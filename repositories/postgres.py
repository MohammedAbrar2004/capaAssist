"""PostgresCapaRepository — the only place raw SQL lives. Implements
`CapaRepository` against the `capa_assist` mirror (`seeds/schema.sql`).
"""

import json
from typing import Optional

from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from models.schemas import (
    ActionTaxonomyEntry,
    AuditTrailEntry,
    Capa,
    CapaAction,
    CapaRCA,
    Category,
    CapaType,
    ContextPackageRecord,
    Employee,
    Evaluation,
    Priority,
    Severity,
    Site,
    Status,
)
from repositories.base import CapaRepository


class PostgresCapaRepository(CapaRepository):
    def __init__(self, pool: ThreadedConnectionPool):
        self._pool = pool
        # Master-data cache (severity/priority/status/capa_type/category) —
        # ~30 rows total across all of these, effectively static for a
        # process's lifetime. Avoids one query per row in N+1-prone call
        # sites (fetch_similar_capas/fetch_effective_actions). Process-local,
        # never invalidated — acceptable staleness tradeoff for masters that
        # change rarely; see phases/production.md if that assumption breaks.
        self._master_cache: dict[tuple[str, str], object] = {}
        # action_taxonomy is static reference data (22 rows total) — cached
        # per action_type at first use, same precedent as _master_cache.
        self._action_taxonomy_cache: dict[str, list[ActionTaxonomyEntry]] = {}

    def _cached(self, table: str, key: Optional[str], fetch_fn):
        if key is None:
            return None
        cache_key = (table, key)
        if cache_key not in self._master_cache:
            self._master_cache[cache_key] = fetch_fn(key)
        return self._master_cache[cache_key]

    def _query(self, sql: str, params: tuple) -> list[dict]:
        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
        finally:
            self._pool.putconn(conn)

    def _execute(self, sql: str, params: tuple) -> None:
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    # --- Core CAPA domain ----------------------------------------------

    def fetch_capa(self, tenant_id: str, capa_id: str) -> Optional[Capa]:
        rows = self._query(
            "SELECT * FROM capa WHERE tenant_id = %s AND capa_id = %s",
            (tenant_id, capa_id),
        )
        return Capa.model_validate(rows[0]) if rows else None

    def fetch_actions(self, tenant_id: str, capa_id: str) -> list[CapaAction]:
        rows = self._query(
            "SELECT * FROM capa_actions WHERE tenant_id = %s AND capa_id = %s"
            " ORDER BY created_date",
            (tenant_id, capa_id),
        )
        return [CapaAction.model_validate(r) for r in rows]

    def fetch_rca(self, tenant_id: str, capa_id: str) -> Optional[CapaRCA]:
        rows = self._query(
            "SELECT * FROM capa_rca WHERE tenant_id = %s AND capa_id = %s",
            (tenant_id, capa_id),
        )
        return CapaRCA.model_validate(rows[0]) if rows else None

    def fetch_actions_bulk(
        self, tenant_id: str, capa_ids: list[str]
    ) -> dict[str, list[CapaAction]]:
        if not capa_ids:
            return {}
        rows = self._query(
            "SELECT * FROM capa_actions WHERE tenant_id = %s AND capa_id = ANY(%s)"
            " ORDER BY capa_id, created_date",
            (tenant_id, capa_ids),
        )
        result: dict[str, list[CapaAction]] = {cid: [] for cid in capa_ids}
        for r in rows:
            result[r["capa_id"]].append(CapaAction.model_validate(r))
        return result

    def fetch_rca_bulk(self, tenant_id: str, capa_ids: list[str]) -> dict[str, CapaRCA]:
        if not capa_ids:
            return {}
        rows = self._query(
            "SELECT * FROM capa_rca WHERE tenant_id = %s AND capa_id = ANY(%s)",
            (tenant_id, capa_ids),
        )
        return {r["capa_id"]: CapaRCA.model_validate(r) for r in rows}

    def fetch_capas_bulk(self, tenant_id: str, capa_ids: list[str]) -> dict[str, Capa]:
        if not capa_ids:
            return {}
        rows = self._query(
            "SELECT * FROM capa WHERE tenant_id = %s AND capa_id = ANY(%s)",
            (tenant_id, capa_ids),
        )
        return {r["capa_id"]: Capa.model_validate(r) for r in rows}

    def fetch_similar_capas(
        self,
        tenant_id: str,
        site_id: Optional[str] = None,
        category_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[Capa]:
        clauses = ["tenant_id = %s"]
        params: list = [tenant_id]
        if site_id is not None:
            clauses.append("site_id = %s")
            params.append(site_id)
        if category_id is not None:
            clauses.append(
                "capa_id IN (SELECT capa_id FROM capa_rca WHERE root_cause_category = %s)"
            )
            params.append(category_id)
        params.append(limit)
        sql = (
            f"SELECT * FROM capa WHERE {' AND '.join(clauses)} "
            "ORDER BY created_date DESC LIMIT %s"
        )
        rows = self._query(sql, tuple(params))
        return [Capa.model_validate(r) for r in rows]

    def fetch_effective_actions(self, tenant_id: str) -> list[CapaAction]:
        rows = self._query(
            """
            SELECT a.* FROM capa_actions a
            JOIN capa_status_master s ON s.status_id = a.status_id
            WHERE a.tenant_id = %s
              AND s.status = 'Closed'
              AND a.verified_date IS NOT NULL
            """,
            (tenant_id,),
        )
        return [CapaAction.model_validate(r) for r in rows]

    def count_recurrence(self, tenant_id: str, capa_id: str) -> int:
        rows = self._query(
            "SELECT recurrence_count FROM capa WHERE tenant_id = %s AND capa_id = %s",
            (tenant_id, capa_id),
        )
        return rows[0]["recurrence_count"] if rows else 0

    def fetch_capas(
        self,
        tenant_id: str,
        limit: int,
        offset: int,
        site_id: Optional[str] = None,
        status_id: Optional[str] = None,
    ) -> list[Capa]:
        clauses, params = self._capa_filter_clauses(tenant_id, site_id, status_id)
        params += [limit, offset]
        sql = (
            f"SELECT * FROM capa WHERE {' AND '.join(clauses)} "
            "ORDER BY created_date DESC LIMIT %s OFFSET %s"
        )
        rows = self._query(sql, tuple(params))
        return [Capa.model_validate(r) for r in rows]

    def count_capas(
        self,
        tenant_id: str,
        site_id: Optional[str] = None,
        status_id: Optional[str] = None,
    ) -> int:
        clauses, params = self._capa_filter_clauses(tenant_id, site_id, status_id)
        sql = f"SELECT COUNT(*) AS n FROM capa WHERE {' AND '.join(clauses)}"
        rows = self._query(sql, tuple(params))
        return rows[0]["n"] if rows else 0

    @staticmethod
    def _capa_filter_clauses(
        tenant_id: str, site_id: Optional[str], status_id: Optional[str]
    ) -> tuple[list[str], list]:
        clauses = ["tenant_id = %s"]
        params: list = [tenant_id]
        if site_id is not None:
            clauses.append("site_id = %s")
            params.append(site_id)
        if status_id is not None:
            clauses.append("status_id = %s")
            params.append(status_id)
        return clauses, params

    def fetch_audit_trail(
        self,
        tenant_id: str,
        capa_id: Optional[str] = None,
        agent: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditTrailEntry]:
        clauses, params = self._audit_filter_clauses(tenant_id, capa_id, agent)
        params += [limit, offset]
        sql = (
            f"SELECT * FROM capa_ai_audit_trail WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at DESC LIMIT %s OFFSET %s"
        )
        rows = self._query(sql, tuple(params))
        return [AuditTrailEntry.model_validate(r) for r in rows]

    def count_audit_trail(
        self,
        tenant_id: str,
        capa_id: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> int:
        clauses, params = self._audit_filter_clauses(tenant_id, capa_id, agent)
        sql = f"SELECT COUNT(*) AS n FROM capa_ai_audit_trail WHERE {' AND '.join(clauses)}"
        rows = self._query(sql, tuple(params))
        return rows[0]["n"] if rows else 0

    @staticmethod
    def _audit_filter_clauses(
        tenant_id: str, capa_id: Optional[str], agent: Optional[str]
    ) -> tuple[list[str], list]:
        clauses = ["tenant_id = %s"]
        params: list = [tenant_id]
        if capa_id is not None:
            clauses.append("input_payload->>'capa_id' = %s")
            params.append(capa_id)
        if agent is not None:
            clauses.append("agent = %s")
            params.append(agent)
        return clauses, params

    # --- Master / lookup -------------------------------------------------

    def fetch_severity(self, severity_id: str) -> Optional[Severity]:
        return self._cached("severity", severity_id, self._fetch_severity_uncached)

    def _fetch_severity_uncached(self, severity_id: str) -> Optional[Severity]:
        rows = self._query(
            "SELECT * FROM mstr_severity_master WHERE severity_id = %s", (severity_id,)
        )
        return Severity.model_validate(rows[0]) if rows else None

    def fetch_priority(self, priority_id: str) -> Optional[Priority]:
        return self._cached("priority", priority_id, self._fetch_priority_uncached)

    def _fetch_priority_uncached(self, priority_id: str) -> Optional[Priority]:
        rows = self._query(
            "SELECT * FROM mstr_priority_master WHERE priority_id = %s", (priority_id,)
        )
        return Priority.model_validate(rows[0]) if rows else None

    def fetch_status(self, status_id: str) -> Optional[Status]:
        return self._cached("status", status_id, self._fetch_status_uncached)

    def _fetch_status_uncached(self, status_id: str) -> Optional[Status]:
        rows = self._query(
            "SELECT * FROM capa_status_master WHERE status_id = %s", (status_id,)
        )
        return Status.model_validate(rows[0]) if rows else None

    def fetch_capa_type(self, capa_type_id: str) -> Optional[CapaType]:
        return self._cached("capa_type", capa_type_id, self._fetch_capa_type_uncached)

    def _fetch_capa_type_uncached(self, capa_type_id: str) -> Optional[CapaType]:
        rows = self._query(
            "SELECT * FROM capa_type_master WHERE capa_type_id = %s", (capa_type_id,)
        )
        return CapaType.model_validate(rows[0]) if rows else None

    def fetch_category(self, category_id: str) -> Optional[Category]:
        return self._cached("category", category_id, self._fetch_category_uncached)

    def _fetch_category_uncached(self, category_id: str) -> Optional[Category]:
        rows = self._query(
            "SELECT * FROM capa_categories WHERE category_id = %s", (category_id,)
        )
        return Category.model_validate(rows[0]) if rows else None

    def fetch_site(self, site_id: str) -> Optional[Site]:
        rows = self._query(
            "SELECT * FROM mstr_tenant_sites WHERE site_id = %s", (site_id,)
        )
        return Site.model_validate(rows[0]) if rows else None

    def fetch_employees(
        self,
        tenant_id: str,
        site_id: Optional[str] = None,
        group_id: Optional[str] = None,
        role_title: Optional[str] = None,
    ) -> list[Employee]:
        clauses = ["tenant_id = %s"]
        params: list = [tenant_id]
        if site_id is not None:
            clauses.append("site_id = %s")
            params.append(site_id)
        if group_id is not None:
            clauses.append("group_id = %s")
            params.append(group_id)
        if role_title is not None:
            clauses.append("role_title ILIKE %s")
            params.append(role_title)
        sql = f"SELECT * FROM mstr_tenant_emp WHERE {' AND '.join(clauses)} ORDER BY full_name"
        rows = self._query(sql, tuple(params))
        return [Employee.model_validate(r) for r in rows]

    def fetch_action_taxonomy(self, action_type: str) -> list[ActionTaxonomyEntry]:
        if action_type not in self._action_taxonomy_cache:
            rows = self._query(
                "SELECT * FROM capa_ai_action_taxonomy WHERE action_type = %s ORDER BY action_taxonomy_id",
                (action_type,),
            )
            self._action_taxonomy_cache[action_type] = [ActionTaxonomyEntry.model_validate(r) for r in rows]
        return self._action_taxonomy_cache[action_type]

    # --- AI-write tables ---------------------------------------------------

    def write_evaluation(self, evaluation: Evaluation) -> None:
        self._execute(
            """
            INSERT INTO capa_ai_evaluations
                (eval_id, action_id, tenant_id, score, weakness_level, dimension_results, model_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                evaluation.eval_id,
                evaluation.action_id,
                evaluation.tenant_id,
                evaluation.score,
                evaluation.weakness_level,
                json.dumps(evaluation.dimension_results),
                evaluation.model_version,
            ),
        )

    def write_audit(self, entry: AuditTrailEntry) -> None:
        self._execute(
            """
            INSERT INTO capa_ai_audit_trail
                (request_id, tenant_id, agent, input_payload, output_payload, user_decision, model_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                entry.request_id,
                entry.tenant_id,
                entry.agent,
                json.dumps(entry.input_payload),
                json.dumps(entry.output_payload),
                entry.user_decision,
                entry.model_version,
            ),
        )

    def save_context_package(self, record: ContextPackageRecord) -> None:
        self._execute(
            """
            INSERT INTO capa_ai_context_packages
                (context_id, request_id, tenant_id, capa_id, package_payload)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                record.context_id,
                record.request_id,
                record.tenant_id,
                record.capa_id,
                json.dumps(record.package_payload),
            ),
        )
