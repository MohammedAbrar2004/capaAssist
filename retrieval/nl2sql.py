"""NL2SQL retrieval system — LLM-generated SQL against a narrow, whitelisted
set of live tables (CAPA domain + masters + MSTR_TENANT_EMP), guarded before
execution. See phases/phase2.md decision 2 for the design rationale.

This is the one place outside repositories/postgres.py where raw SQL is
executed at runtime — an explicit, documented exception (mirroring the
seeds/ exemption) because LLM-generated SQL can't be forced through the
repository's fixed, parameterized methods. Every query here:
  - must be a single SELECT (no UNION/CTE/multi-statement/DDL/DML)
  - must reference only whitelisted tables
  - must include an explicit TENANT_ID = %(tenant_id)s filter (verified by
    regex, not trusted blindly — the value itself is still passed as a bound
    parameter, never string-interpolated)
  - runs against the capa_ai_readonly role (NL2SQL_DATABASE_URL), which only
    has SELECT granted on the whitelist (seeds/seed_readonly_role.sql) — a
    second, independent enforcement layer below the application-level guard
  - gets a LIMIT appended if the model omitted one
  - runs with a short statement_timeout so a pathological query can't hang

A guard failure or DB error returns an empty NL2SQLResult rather than
raising — a bad NL2SQL answer should degrade the context package, not crash
the request.
"""

import logging
import re

import psycopg2
import psycopg2.extras
from pydantic import BaseModel

import config
from models.schemas import NL2SQLResult
from services.llm import call_llm_json

logger = logging.getLogger("capa_ai.nl2sql")

WHITELISTED_TABLES = {
    "capa",
    "capa_actions",
    "capa_rca",
    "capa_investigations",
    "capa_reviews",
    "capa_closure",
    "capa_categories",
    "capa_subcategories",
    "capa_type_master",
    "capa_status_master",
    "mstr_severity_master",
    "mstr_priority_master",
    "mstr_status_master",
    "mstr_tenant_metadata",
    "mstr_tenant_sites",
    "mstr_tenant_groups",
    "mstr_tenant_site_groups",
    "mstr_tenant_emp",
    "mstr_users_metadata",
}

_FORBIDDEN_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create", "grant",
    "revoke", "truncate", "exec", "execute", "attach", "copy", "merge",
    "union", "with", "into", "vacuum", "call",
)
_TENANT_FILTER_RE = re.compile(r"tenant_id\s*=\s*%\(tenant_id\)s", re.IGNORECASE)
_TABLE_REF_RE = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][\w]*)", re.IGNORECASE)
_STATEMENT_TIMEOUT_MS = 5000
_DEFAULT_LIMIT = 50

# Real column names for the whitelisted tables — without this the model
# hallucinates plausible-but-wrong columns (observed: ehs_officer_id,
# first_name/last_name) since it only ever knows the table names otherwise.
_SCHEMA_DESCRIPTION = """\
capa(capa_id, tenant_id, site_id, owner_group_id, capa_title, capa_description, root_cause,
     priority_id, severity_id, capa_type_id, status_id, assigned_to, due_date, is_recurring,
     recurrence_count, linked_capa_ids)
capa_actions(action_id, capa_id, tenant_id, site_id, action_title, action_description,
     priority_id, capa_type_id, severity_id, assigned_to, status_id, due_date,
     verified_by, verified_date)
capa_rca(rca_id, capa_id, tenant_id, contributing_factors, failed_controls, missing_controls,
     root_cause_category)
capa_investigations(investigation_id, capa_id, tenant_id, site_id, investigation_title,
     investigation_description, investigator_email, investigation_outcome)
capa_reviews(review_id, capa_id, tenant_id, site_id, reviewed_by, review_outcome,
     reviewer_comments, review_date)
capa_closure(closure_id, capa_id, tenant_id, site_id, closed_by, closure_date, closure_status,
     approval_status)
capa_categories(category_id, tenant_id, category_name, category_description)
capa_subcategories(subcategory_id, category_id, tenant_id, subcategory_name)
capa_type_master(capa_type_id, tenant_id, capa_type_name, capa_type_description)
capa_status_master(status_id, tenant_id, status, status_description, source_table)
mstr_severity_master(severity_id, severity_name, severity_level, description)
mstr_priority_master(priority_id, priority_level, description)
mstr_status_master(status_id, status, status_description, source_table)
mstr_tenant_metadata(tenant_id, tenant_name, domain, contact_name, contact_email)
mstr_tenant_sites(site_id, tenant_id, site_name, site_manager, latitude, longitude)
mstr_tenant_groups(group_id, tenant_id, group_name, group_description, group_manager_email)
mstr_tenant_site_groups(tenant_id, site_id, group_id)
mstr_tenant_emp(emp_id, tenant_id, site_id, group_id, user_email, full_name, role_title,
     role_description, status_id)
mstr_users_metadata(user_email, tenant_id, full_name, group_id, status_id)
"""


class _NL2SQLLLMOutput(BaseModel):
    sql: str


# Sub-Phase 2b hardening (phases/phase2.md): the fixed "list employees at
# site X" question regardless of CAPA content underused NL2SQL. Map
# root_cause_category -> the role keyword actually relevant to that failure
# mode, so the one NL2SQL call we make is the useful one for this CAPA.
_CATEGORY_ROLE_KEYWORDS = {
    "CAT_TRAINING_GAP": "training or HR",
    "CAT_EQUIPMENT_FAULT": "maintenance or engineering",
    "CAT_PROCESS_FAILURE": "process or quality",
    "CAT_MISSING_INSPECTION": "safety inspector or EHS",
    "CAT_MANAGEMENT_SYSTEM_WEAKNESS": "EHS management or compliance",
    "CAT_ENGINEERING_CONTROL_GAP": "engineering or maintenance",
    "CAT_HUMAN_ERROR": "safety inspector or EHS",
    "CAT_ENVIRONMENTAL_FACTOR": "EHS or maintenance",
}


def build_employee_question(site_id: str, root_cause_category: str | None) -> str:
    role_hint = _CATEGORY_ROLE_KEYWORDS.get(root_cause_category) if root_cause_category else None
    if role_hint:
        return (
            f"List employees with {role_hint} roles at site {site_id}, "
            "who could own or contribute to this CAPA."
        )
    return f"List employees and their roles at site {site_id}."


class GuardRejection(Exception):
    pass


def _guard(sql: str) -> str:
    """Raises GuardRejection if sql fails any check. Returns the (possibly
    LIMIT-appended) sql to execute on success."""
    text = sql.strip()
    if text.endswith(";"):
        text = text[:-1].strip()
    if ";" in text:
        raise GuardRejection("multi-statement query rejected")

    if not re.match(r"^\s*select\b", text, re.IGNORECASE):
        raise GuardRejection("only SELECT statements are allowed")

    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", text, re.IGNORECASE):
            raise GuardRejection(f"forbidden keyword: {kw}")

    if "--" in text or "/*" in text:
        raise GuardRejection("comment markers are not allowed")

    tables = {m.group(1).lower() for m in _TABLE_REF_RE.finditer(text)}
    unknown = tables - WHITELISTED_TABLES
    if unknown:
        raise GuardRejection(f"non-whitelisted table(s): {sorted(unknown)}")

    if not _TENANT_FILTER_RE.search(text):
        raise GuardRejection("missing required TENANT_ID = %(tenant_id)s filter")

    if not re.search(r"\blimit\s+\d+", text, re.IGNORECASE):
        text = f"{text} LIMIT {_DEFAULT_LIMIT}"

    # psycopg2 treats every literal '%' as a format directive once params
    # are passed — escape any '%' the model wrote into string literals
    # (e.g. ILIKE '%foo%') without touching our own %(tenant_id)s placeholder.
    placeholder = "%(tenant_id)s"
    text = placeholder.join(part.replace("%", "%%") for part in text.split(placeholder))

    return text


async def run_nl2sql(question: str, tenant_id: str) -> NL2SQLResult:
    prompt = (
        "Write a single PostgreSQL SELECT statement to answer this question:\n"
        f"{question}\n\n"
        "Allowed tables and their real columns (use ONLY these — do not invent "
        f"column names):\n{_SCHEMA_DESCRIPTION}\n"
        "You MUST include a WHERE clause filtering on tenant_id = %(tenant_id)s "
        "literally (that exact placeholder syntax — do not substitute a value).\n"
        "No UNION, no CTEs (WITH), no subqueries into other databases, no DDL/DML. "
        "Single SELECT only, optionally with JOINs across the allowed tables."
    )
    try:
        llm_out = await call_llm_json(
            [{"role": "user", "content": prompt}], config.PRIMARY_MODEL, _NL2SQLLLMOutput, max_tokens=1200
        )
        sql = _guard(llm_out.sql)
    except (GuardRejection, ValueError) as exc:
        logger.warning("nl2sql guard/LLM rejected query for question=%r: %s", question, exc)
        return NL2SQLResult(question=question, sql="", row_count=0, rows=[])

    try:
        conn = psycopg2.connect(config.NL2SQL_DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"SET statement_timeout = {_STATEMENT_TIMEOUT_MS}")
                cur.execute(sql, {"tenant_id": tenant_id})
                rows = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("nl2sql execution failed for question=%r: %s", question, exc)
        return NL2SQLResult(question=question, sql=sql, row_count=0, rows=[])

    return NL2SQLResult(question=question, sql=sql, row_count=len(rows), rows=rows)
