"""1b.2 — Loader.

Reads the JSON emitted by `build_seed_data.py` and inserts it into the
mirrored Postgres schema in FK order:
tenant -> sites -> groups -> site_groups -> users -> masters -> CAPA ->
actions -> RCA -> investigations -> reviews -> closures.

Idempotent: deletes any existing rows for TENANT_ACERTECH (in reverse FK
order) before inserting, so it's safe to re-run. Raw SQL lives here only as
seed-tooling, per CLAUDE.md's exemption for `seeds/` — runtime code must
still go through PostgresCapaRepository.

Run: `python seeds/load_seed.py`
"""

import json
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

DATA_DIR = Path(__file__).parent / "data"
TENANT_ID = config.CAPA_TENANT_ID or "TENANT_ACERTECH"


def _load(filename: str):
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def _delete_existing(cur) -> None:
    # Reverse FK order. capa_ai_* tables are seed-irrelevant (Phase 2+ writes
    # them at runtime) but cleared too in case a prior failed run left rows.
    tenant_scoped_tables = [
        "capa_ai_context_packages",
        "capa_ai_audit_trail",
        "capa_ai_evaluations",
        "CAPA_CLOSURE",
        "CAPA_REVIEWS",
        "CAPA_INVESTIGATIONS",
        "CAPA_RCA",
        "CAPA_ACTIONS",
        "CAPA",
        "CAPA_CATEGORIES",
        "CAPA_TYPE_MASTER",
        "CAPA_STATUS_MASTER",
        "MSTR_TENANT_EMP",
        "MSTR_USERS_METADATA",
        "MSTR_TENANT_SITE_GROUPS",
        "MSTR_TENANT_GROUPS",
        "MSTR_TENANT_SITES",
        "MSTR_TENANT_METADATA",
    ]
    for table in tenant_scoped_tables:
        cur.execute(f"DELETE FROM {table} WHERE TENANT_ID = %s", (TENANT_ID,))
    # MSTR_SEVERITY_MASTER / MSTR_PRIORITY_MASTER are tenant-agnostic globals —
    # delete by the specific minted IDs instead.
    cur.execute("DELETE FROM MSTR_SEVERITY_MASTER WHERE SEVERITY_ID LIKE 'SEV_%%'")
    cur.execute("DELETE FROM MSTR_PRIORITY_MASTER WHERE PRIORITY_ID LIKE 'PRI_%%'")
    cur.execute("DELETE FROM MSTR_STATUS_MASTER WHERE STATUS_ID = %s", ("STATUS_ACTIVE",))


def load(conn) -> None:
    cur = conn.cursor()
    _delete_existing(cur)

    mstr_status = _load("mstr_status.json")
    for row in mstr_status:
        cur.execute(
            """INSERT INTO MSTR_STATUS_MASTER (STATUS_ID, STATUS, STATUS_DESCRIPTION, SOURCE_TABLE)
               VALUES (%s, %s, %s, %s) ON CONFLICT (STATUS_ID) DO NOTHING""",
            (row["status_id"], row["status"], row["status_description"], row["source_table"]),
        )

    tenant = _load("tenant.json")
    cur.execute(
        """INSERT INTO MSTR_TENANT_METADATA (TENANT_ID, TENANT_NAME, DOMAIN, STATUS_ID, CONTACT_NAME, CONTACT_EMAIL)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (tenant["tenant_id"], tenant["tenant_name"], tenant["domain"], tenant["status_id"],
         tenant["contact_name"], tenant["contact_email"]),
    )

    for s in _load("sites.json"):
        cur.execute(
            """INSERT INTO MSTR_TENANT_SITES (SITE_ID, TENANT_ID, SITE_NAME, STATUS_ID, META)
               VALUES (%s, %s, %s, %s, %s)""",
            (s["site_id"], s["tenant_id"], s["site_name"], s["status_id"], s.get("meta")),
        )

    for g in _load("groups.json"):
        cur.execute(
            """INSERT INTO MSTR_TENANT_GROUPS (GROUP_ID, TENANT_ID, GROUP_NAME, GROUP_DESCRIPTION, GROUP_MANAGER_EMAIL, STATUS_ID)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (g["group_id"], g["tenant_id"], g["group_name"], g["group_description"],
             g.get("group_manager_email"), g["status_id"]),
        )

    for sg in _load("site_groups.json"):
        cur.execute(
            """INSERT INTO MSTR_TENANT_SITE_GROUPS (TENANT_ID, SITE_ID, GROUP_ID)
               VALUES (%s, %s, %s)""",
            (sg["tenant_id"], sg["site_id"], sg["group_id"]),
        )

    for u in _load("users.json"):
        cur.execute(
            """INSERT INTO MSTR_USERS_METADATA (USER_EMAIL, TENANT_ID, FULL_NAME, STATUS_ID, GROUP_ID)
               VALUES (%s, %s, %s, %s, %s)""",
            (u["user_email"], u["tenant_id"], u["full_name"], u["status_id"], u.get("group_id")),
        )

    for e in _load("employees.json"):
        cur.execute(
            """INSERT INTO MSTR_TENANT_EMP (EMP_ID, TENANT_ID, SITE_ID, GROUP_ID, USER_EMAIL,
                   FULL_NAME, ROLE_TITLE, ROLE_DESCRIPTION, STATUS_ID)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (e["emp_id"], e["tenant_id"], e["site_id"], e["group_id"], e["user_email"],
             e["full_name"], e["role_title"], e["role_description"], e["status_id"]),
        )

    for sev in _load("severities.json"):
        cur.execute(
            """INSERT INTO MSTR_SEVERITY_MASTER (SEVERITY_ID, SEVERITY_NAME, SEVERITY_LEVEL, DISPLAY_ORDER, DESCRIPTION)
               VALUES (%s, %s, %s, %s, %s) ON CONFLICT (SEVERITY_ID) DO NOTHING""",
            (sev["severity_id"], sev["severity_name"], sev["severity_level"], sev["display_order"], sev.get("description")),
        )

    for pri in _load("priorities.json"):
        cur.execute(
            """INSERT INTO MSTR_PRIORITY_MASTER (PRIORITY_ID, PRIORITY_LEVEL, DISPLAY_ORDER, DESCRIPTION)
               VALUES (%s, %s, %s, %s) ON CONFLICT (PRIORITY_ID) DO NOTHING""",
            (pri["priority_id"], pri["priority_level"], pri["display_order"], pri.get("description")),
        )

    for st in _load("capa_statuses.json"):
        cur.execute(
            """INSERT INTO CAPA_STATUS_MASTER (STATUS_ID, TENANT_ID, STATUS, STATUS_DESCRIPTION, SOURCE_TABLE)
               VALUES (%s, %s, %s, %s, %s)""",
            (st["status_id"], st["tenant_id"], st["status"], st["status_description"], st["source_table"]),
        )

    for ct in _load("capa_types.json"):
        cur.execute(
            """INSERT INTO CAPA_TYPE_MASTER (CAPA_TYPE_ID, TENANT_ID, CAPA_TYPE_NAME, CAPA_TYPE_DESCRIPTION)
               VALUES (%s, %s, %s, %s)""",
            (ct["capa_type_id"], ct["tenant_id"], ct["capa_type_name"], ct.get("capa_type_description")),
        )

    for cat in _load("categories.json"):
        cur.execute(
            """INSERT INTO CAPA_CATEGORIES (CATEGORY_ID, TENANT_ID, CATEGORY_NAME, CATEGORY_DESCRIPTION, CREATED_BY)
               VALUES (%s, %s, %s, %s, %s)""",
            (cat["category_id"], cat["tenant_id"], cat["category_name"], cat.get("category_description"), cat["created_by"]),
        )

    for c in _load("capas.json"):
        cur.execute(
            """INSERT INTO CAPA (CAPA_ID, TENANT_ID, SITE_ID, SOURCE_MODULE, SOURCE_RECORD_ID,
                   OWNER_GROUP_ID, CAPA_TITLE, CAPA_DESCRIPTION, RCA_METHOD_ID, ROOT_CAUSE,
                   PRIORITY_ID, SEVERITY_ID, CAPA_TYPE_ID, STATUS_ID, CREATED_BY, ASSIGNED_TO,
                   DUE_DATE, COMPLETED_DATE, CAPA_CLOSURE_DATE, RECURRENCE_COUNT,
                   LINKED_CAPA_IDS, IS_RECURRING)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (c["capa_id"], c["tenant_id"], c["site_id"], c["source_module"], c["source_record_id"],
             c["owner_group_id"], c["capa_title"], c["capa_description"], c["rca_method_id"], c["root_cause"],
             c["priority_id"], c["severity_id"], c["capa_type_id"], c["status_id"], c["created_by"], c["assigned_to"],
             c["due_date"], c["completed_date"], c["capa_closure_date"], c["recurrence_count"],
             c["linked_capa_ids"], c["is_recurring"]),
        )

    for a in _load("actions.json"):
        cur.execute(
            """INSERT INTO CAPA_ACTIONS (ACTION_ID, CAPA_ID, TENANT_ID, SITE_ID, ACTION_TITLE,
                   ACTION_DESCRIPTION, PRIORITY_ID, CAPA_TYPE_ID, SEVERITY_ID, CREATED_BY,
                   ASSIGNED_TO, STATUS_ID, DUE_DATE, COMPLETION_DATE, VERIFICATION_REQUIRED,
                   VERIFIED_BY, VERIFIED_DATE, EVIDENCE_REQUIRED)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (a["action_id"], a["capa_id"], a["tenant_id"], a["site_id"], a["action_title"],
             a["action_description"], a["priority_id"], a["capa_type_id"], a["severity_id"], a["created_by"],
             a["assigned_to"], a["status_id"], a["due_date"], a["completion_date"], a["verification_required"],
             a["verified_by"], a["verified_date"], a["evidence_required"]),
        )

    for r in _load("rca.json"):
        cur.execute(
            """INSERT INTO CAPA_RCA (RCA_ID, CAPA_ID, TENANT_ID, CONTRIBUTING_FACTORS,
                   FAILED_CONTROLS, MISSING_CONTROLS, ROOT_CAUSE_CATEGORY)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (r["rca_id"], r["capa_id"], r["tenant_id"], r["contributing_factors"],
             r["failed_controls"], r["missing_controls"], r["root_cause_category"]),
        )

    for inv in _load("investigations.json"):
        cur.execute(
            """INSERT INTO CAPA_INVESTIGATIONS (INVESTIGATION_ID, CAPA_ID, TENANT_ID, SITE_ID,
                   INVESTIGATION_TITLE, INVESTIGATION_DESCRIPTION, INVESTIGATOR_EMAIL, INVESTIGATION_OUTCOME)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (inv["investigation_id"], inv["capa_id"], inv["tenant_id"], inv["site_id"],
             inv["investigation_title"], inv["investigation_description"], inv["investigator_email"],
             inv["investigation_outcome"]),
        )

    for rev in _load("reviews.json"):
        cur.execute(
            """INSERT INTO CAPA_REVIEWS (REVIEW_ID, CAPA_ID, TENANT_ID, SITE_ID, REVIEWED_BY,
                   REVIEW_OUTCOME, REVIEW_ITERATION, REVIEWER_COMMENTS, REVIEW_DATE, REVIEW_TYPE,
                   RECURRING_REVIEW)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (rev["review_id"], rev["capa_id"], rev["tenant_id"], rev["site_id"], rev["reviewed_by"],
             rev["review_outcome"], rev["review_iteration"], rev["reviewer_comments"], rev["review_date"],
             rev["review_type"], rev["recurring_review"]),
        )

    for cl in _load("closures.json"):
        cur.execute(
            """INSERT INTO CAPA_CLOSURE (CLOSURE_ID, CAPA_ID, TENANT_ID, SITE_ID, CLOSED_BY,
                   CLOSURE_DATE, CLOSURE_STATUS, APPROVAL_STATUS, APPROVED_BY, CLOSURE_COMMENTS,
                   COMMENTED_BY, COMMENTED_DATE)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (cl["closure_id"], cl["capa_id"], cl["tenant_id"], cl["site_id"], cl["closed_by"],
             cl["closure_date"], cl["closure_status"], cl["approval_status"], cl["approved_by"],
             cl["closure_comments"], cl["commented_by"], cl["commented_date"]),
        )

    conn.commit()
    print(f"Seed load complete for tenant {TENANT_ID}.")


def main() -> None:
    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        load(conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
