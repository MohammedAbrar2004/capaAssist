"""Integration tests for PostgresCapaRepository against the seeded dev DB.

Formalizes the Checkpoint 1b manual verification from phases/phase1.md into
pytest, plus the description/META fills added when wrapping Phase 1. Asserts
against the fixed 40-CAPA seed (TENANT_ACERTECH), so it doubles as a
regression guard on the seed loader.

Run (from service/, conda env capa-ai):
    pytest tests/integration/test_postgres_repository.py -v
The suite self-skips if the dev DB is unreachable (see conftest).
"""

import uuid

from models.schemas import (
    AuditTrailEntry,
    Capa,
    CapaAction,
    ContextPackageRecord,
    Evaluation,
)
from repositories.postgres import PostgresCapaRepository


# --- Factory / wiring -------------------------------------------------------

def test_repository_is_postgres(repo):
    assert isinstance(repo, PostgresCapaRepository)


# --- Core CAPA reads + master resolution ------------------------------------

def test_fetch_capa_resolves_master_values(repo, tenant):
    capa = repo.fetch_capa(tenant, "CAPA_0001")
    assert isinstance(capa, Capa)
    assert capa.capa_id == "CAPA_0001"
    assert repo.fetch_severity(capa.severity_id).severity_name == "High"
    assert repo.fetch_priority(capa.priority_id).priority_level == "High"
    assert repo.fetch_status(capa.status_id).status == "Closed"
    assert repo.fetch_capa_type(capa.capa_type_id).capa_type_name == "Corrective"


def test_fetch_capa_unknown_returns_none(repo, tenant):
    assert repo.fetch_capa(tenant, "CAPA_NOPE") is None


def test_fetch_actions_returns_two_for_capa_0001(repo, tenant):
    actions = repo.fetch_actions(tenant, "CAPA_0001")
    assert len(actions) == 2
    assert all(isinstance(a, CapaAction) for a in actions)
    assert all(a.capa_id == "CAPA_0001" for a in actions)


def test_fetch_similar_capas_filters_by_site_and_category(repo, tenant):
    similar = repo.fetch_similar_capas(
        tenant, site_id="SITE_05", category_id="CAT_TRAINING_GAP"
    )
    ids = {c.capa_id for c in similar}
    # CAPA 7 + recurrence Cluster B (31..35) are the only Site-5 / Training-Gap CAPAs.
    assert ids == {"CAPA_0007", "CAPA_0031", "CAPA_0032", "CAPA_0033", "CAPA_0034", "CAPA_0035"}


def test_fetch_rca_returns_controls(repo, tenant):
    rca = repo.fetch_rca(tenant, "CAPA_0030")
    assert rca is not None
    assert rca.missing_controls  # non-empty for this CAPA
    assert rca.root_cause_category == "CAT_EQUIPMENT_FAULT"


def test_recurrence_chain_capa_0030(repo, tenant):
    capa = repo.fetch_capa(tenant, "CAPA_0030")
    assert capa.is_recurring == 1
    assert capa.recurrence_count == 5
    assert repo.count_recurrence(tenant, "CAPA_0030") == 5
    assert capa.linked_capa_ids == "CAPA_0001,CAPA_0026,CAPA_0027,CAPA_0028,CAPA_0029"


def test_fetch_effective_actions_nonempty(repo, tenant):
    actions = repo.fetch_effective_actions(tenant)
    assert actions  # at least some verified, closed actions exist in the seed
    assert all(a.verified_date is not None for a in actions)


# --- Description / META fills (Phase 1 wrap-up) -----------------------------

def test_master_descriptions_populated(repo):
    assert repo.fetch_severity("SEV_HIGH").description
    assert repo.fetch_priority("PRI_HIGH").description
    assert repo.fetch_capa_type("TYPE_CORRECTIVE").capa_type_description
    assert repo.fetch_category("CAT_TRAINING_GAP").category_description


def test_site_meta_populated(repo):
    site = repo.fetch_site("SITE_01")
    assert site is not None
    assert site.meta  # human-readable site description stored in META


# --- AI-write tables round-trip ---------------------------------------------

def test_write_audit_round_trips(repo, tenant, db_conn):
    rid = f"TEST_{uuid.uuid4().hex[:12]}"
    repo.write_audit(
        AuditTrailEntry(
            request_id=rid,
            tenant_id=tenant,
            agent="test_agent",
            input_payload={"k": "in"},
            output_payload={"k": "out"},
            model_version="test-1",
        )
    )
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT agent, input_payload, output_payload FROM capa_ai_audit_trail WHERE request_id = %s",
                (rid,),
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] == "test_agent"
        assert row[1] == {"k": "in"}  # JSONB survives round-trip
        assert row[2] == {"k": "out"}
    finally:
        _cleanup(db_conn, "capa_ai_audit_trail", "request_id", rid)


def test_write_evaluation_round_trips(repo, tenant, db_conn):
    eid = f"TEST_{uuid.uuid4().hex[:12]}"
    repo.write_evaluation(
        Evaluation(
            eval_id=eid,
            action_id="ACTION_0001",
            tenant_id=tenant,
            score=72.5,
            weakness_level="Acceptable",
            dimension_results={"specificity": 0.8},
            model_version="test-1",
        )
    )
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT score, weakness_level, dimension_results FROM capa_ai_evaluations WHERE eval_id = %s",
                (eid,),
            )
            row = cur.fetchone()
        assert row is not None
        assert float(row[0]) == 72.5
        assert row[1] == "Acceptable"
        assert row[2] == {"specificity": 0.8}
    finally:
        _cleanup(db_conn, "capa_ai_evaluations", "eval_id", eid)


def test_save_context_package_round_trips(repo, tenant, db_conn):
    rid = f"TEST_{uuid.uuid4().hex[:12]}"
    cid = f"TEST_{uuid.uuid4().hex[:12]}"
    # context package FKs to an audit row — create that first.
    repo.write_audit(
        AuditTrailEntry(
            request_id=rid, tenant_id=tenant, agent="test_agent",
            input_payload={}, output_payload={},
        )
    )
    repo.save_context_package(
        ContextPackageRecord(
            context_id=cid,
            request_id=rid,
            tenant_id=tenant,
            capa_id="CAPA_0001",
            package_payload={"ctx": "value"},
        )
    )
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT package_payload FROM capa_ai_context_packages WHERE context_id = %s",
                (cid,),
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] == {"ctx": "value"}
    finally:
        _cleanup(db_conn, "capa_ai_context_packages", "context_id", cid)
        _cleanup(db_conn, "capa_ai_audit_trail", "request_id", rid)


def _cleanup(conn, table: str, key_col: str, key_val: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table} WHERE {key_col} = %s", (key_val,))
    conn.commit()
