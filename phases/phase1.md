# Phase 1 — Database Schema + Seed Data

**Status:** **PHASE 1 COMPLETE.** Sub-Phase 1a (Setup) complete, Checkpoint 1a passed. Sub-Phase 1b (Seeding) complete, Checkpoint 1b passed. Wrap-up pass done (description/META fills + formalized integration pytest — see "Phase 1 Wrap-Up" below). Architecture = **PostgreSQL `capa_assist` mirror of the relevant subset of the real Oracle schema, behind a swappable repository layer.** The live Oracle DB is **not** touched during the build; the backend can be swapped to Oracle later by adding one repository class + flipping `DB_BACKEND` (and the Postgres impl can then be deleted as one self-contained file).

This file is the single source of truth for Phase 1. It holds the final schema/seed plan; the Implementation / How to Run / How to Test sections get filled in as sub-phases 1a and 1b are built.

---

## Major Discovery — the real production schema

The user shared `version2/schema.csv` — a dump of the **actual production SoapBox.Cloud CAPA module schema** (from Oracle `user_tab_columns`). This is fundamentally different from the reference project, which was built against a simplified, invented 12-table PostgreSQL schema (`capas`, `capa_actions`, `capa_root_causes`, `sites`, `departments`, `employees`, `assets`, `root_cause_taxonomy`, ...).

Differences that matter for the rebuild:

| Aspect | Reference (toy) | Real production (schema.csv) |
|---|---|---|
| Engine | PostgreSQL | **Oracle** (`VARCHAR2`, `CLOB`, `NUMBER`, `RAW(16)`, `SDO_GEOMETRY`, `TIMESTAMP(6) WITH TIME ZONE`) |
| Tenancy | Single org (AcerTech) | **Multi-tenant** — `TENANT_ID` on nearly every table |
| IDs | SERIAL ints | `VARCHAR2(50)` strings; some `RAW(16)` GUIDs |
| Org model | sites / departments / employees / assets | tenants / sites / groups / users-by-email. **No assets, no departments, no employees tables.** |
| Root cause | `capa_root_causes.root_cause_category` (taxonomy FK) | `CAPA.ROOT_CAUSE` (free CLOB) + `CAPA.RCA_METHOD_ID` + `CAPA_INVESTIGATIONS`. **No category taxonomy column.** |
| Recurrence | broken/derived | **Native**: `CAPA.IS_RECURRING`, `CAPA.RECURRENCE_COUNT`, `CAPA.LINKED_CAPA_IDS` |
| Effectiveness | `capa_actions.effectiveness_result` + `strength_label` | Spread across `CAPA_REVIEWS.REVIEW_OUTCOME`, `CAPA_ACTIONS.VERIFIED_BY/VERIFIED_DATE`, `CAPA_CLOSURE.CLOSURE_STATUS`, `CAPA_INVESTIGATIONS.INVESTIGATION_OUTCOME` |

Consequence: the reference's data model, seed SQL, and the whole "root_cause_category taxonomy + effectiveness_result + strength_label" intelligence design do **not** port 1:1. They have to be re-mapped onto the real schema's concepts.

---

## Table Triage

Full schema = ~50 tables. Most are platform plumbing irrelevant to the AI service. Classification:

### Tier 1 — Core CAPA domain (AI reasons about these directly)
- **`CAPA`** — master record. Key cols: `CAPA_ID, TENANT_ID, SITE_ID, SOURCE_MODULE, SOURCE_RECORD_ID, OWNER_GROUP_ID, CAPA_TITLE, CAPA_DESCRIPTION, RCA_METHOD_ID, ROOT_CAUSE, PRIORITY_ID, SEVERITY_ID, CAPA_TYPE_ID, STATUS_ID, ASSIGNED_TO, DUE_DATE, COMPLETED_DATE, CAPA_CLOSURE_DATE, RECURRENCE_COUNT, LINKED_CAPA_IDS, IS_RECURRING, RISK_LEVEL, REGULATORY_REQUIREMENT, BUSINESS_IMPACT`
- **`CAPA_ACTIONS`** — the actions generated/evaluated/improved. Key cols: `ACTION_ID, CAPA_ID, ACTION_TITLE, ACTION_DESCRIPTION, PRIORITY_ID, CAPA_TYPE_ID, SEVERITY_ID, ASSIGNED_TO, STATUS_ID, DUE_DATE, COMPLETION_DATE, VERIFICATION_REQUIRED, VERIFIED_BY, VERIFIED_DATE, BLOCKED_BY, DEPENDENCY_TYPE`
- **`CAPA_INVESTIGATIONS`** — RCA data. `INVESTIGATION_TITLE/DESCRIPTION, INVESTIGATION_OUTCOME, INVESTIGATOR_EMAIL`
- **`CAPA_REVIEWS`** (+ `CAPA_REVIEW_HISTORY`, `CAPA_REVIEW_TASKS`) — review outcomes = effectiveness signal. `REVIEW_OUTCOME, REVIEW_TYPE, NEXT_REVIEW_DATE, RECURRING_REVIEW`
- **`CAPA_ACTION_PLAN`** — action planning detail (planned/actual start-end, owner, status)
- **`CAPA_CLOSURE`** — closure + verification. `CLOSURE_STATUS, APPROVAL_STATUS`
- **`CAPA_APPROVALS`** — approval workflow (human-in-the-loop signal)
- **`CAPA_CATEGORIES`** / **`CAPA_SUBCATEGORIES`** — categorization; `CAPA_CATEGORIES` holds the root-cause category controlled vocab in the mirror

### Tier 2 — Master / lookup (resolve IDs → names, org context)
- **`MSTR_SEVERITY_MASTER`** — `SEVERITY_ID → SEVERITY_NAME, SEVERITY_LEVEL`
- **`MSTR_PRIORITY_MASTER`** — `PRIORITY_ID → PRIORITY_LEVEL`
- **`CAPA_STATUS_MASTER`** + **`MSTR_STATUS_MASTER`** — `STATUS_ID → STATUS` (note: `SOURCE_TABLE` col implies status sets are per-table)
- **`CAPA_TYPE_MASTER`** — `CAPA_TYPE_ID → CAPA_TYPE_NAME` (likely Containment/Corrective/Preventive/Risk Mitigation)
- **`MSTR_TENANT_METADATA`** — tenants = the "enterprise/org" concept
- **`MSTR_TENANT_SITES`** — sites (`SITE_NAME, LAT/LONG, SITE_MANAGER`)
- **`MSTR_TENANT_GROUPS`** (+ `MSTR_TENANT_SITE_GROUPS`) — owner groups → maps `CAPA.OWNER_GROUP_ID`
- **`MSTR_USERS_METADATA`** — users (PK `USER_EMAIL`, `FULL_NAME`) → resolve `ASSIGNED_TO/CREATED_BY`
- **`CAPA_SLA_RULES`** + **`CAPA_ESCALATION_LEVELS`** + **`MSTR_HOLIDAY_CALENDAR`** — due-date realism (severity/priority → SLA hours), useful for the due_date_quality scoring dimension

### Tier 3 — Supporting (maybe, depending on agent design)
- `CAPA_CHECKLIST_MASTER` / `CAPA_CHECKLIST_ITEMS` / `CAPA_CHECKLIST_RESPONSE_EVIDENCES` — evidence/checklist requirements (could inform evidence_requirement dimension)
- `CAPA_COMMENTS`, `CAPA_DOCUMENTS`, `CAPA_ATTACHMENTS` — supporting evidence trail
- `CAPA_TEMPLATES` — templates (could inform generation)
- `CAPA_AUDIT_LOGS` — CAPA-specific audit
- `CAPA_MODULE_USERS` — who has CAPA access + role
- `CAPA_NOTIFICATIONS` — workflow automation

### Tier 4 — AI-service-specific (NEW — do not exist in production schema, we create them)
- `capa_ai_evaluations` — scoring history (eval_id, action_id, score, weakness_level, dimension_results JSON, ...)
- `capa_ai_audit_trail` — every AI interaction (request_id, agent, input/output, user_decision, model_version)
- `capa_ai_context_packages` — context trail per AI call
- `CAPA_RCA` — root-cause-analysis fields (`contributing_factors` / `failed_controls` / `missing_controls` / `root_cause_category`); AI-side extension, see Source → Mirror Mapping
- Recurrence: derived from native `CAPA.IS_RECURRING`/`RECURRENCE_COUNT`/`LINKED_CAPA_IDS` — no separate tracking table
- Root-cause category: stored on `CAPA_RCA`, referencing the `CAPA_CATEGORIES` vocab — no separate taxonomy table

**This inventory is Phase 1 snapshot, not current state.** Two more Tier-4-style AI-side tables were added in later phases, each documented where added: `MSTR_TENANT_EMP` (Phase 2 — employee/org-directory, see `phases/phase2.md` decision 1) and `CAPA_AI_ACTION_TAXONOMY` (Phase 3 — action_type × theme reference data for the Generator, see `phases/phase3.md` decision 2).

### Tier 5 — IRRELEVANT to the AI service (auth / session / billing / APEX / Oracle internals)
`APP_DRAFTS`, `DBTOOLS$EXECUTION_HISTORY`, `HTMLDB_PLAN_TABLE`, `TEMP`, `TEMP_USER_PREFERENCE`, `MSTR_APEX_COMPONENT_AUTH_MAP`, `MSTR_APEX_PAGE_AUTH_MAP`, `MSTR_LOGIN_HISTORY`, `MSTR_USER_SESSIONS`, `MSTR_RESET_PASSWORD_TOKENS`, `MSTR_USER_PREFERENCES`, `MSTR_USER_PREFERENCES_HISTORY`, `MSTR_FEATURE_FLAGS`, `MSTR_SUBSCRIPTION_PLANS`, `MSTR_TENANT_SUBSCRIPTIONS`, `MSTR_TENANT_SETTINGS`, `MSTR_TENANT_CUSTOM_ATTRIBUTE_VALUES`, `MSTR_ROLE_MASTER`, `MSTR_ROLE_PERMISSIONS`, `MSTR_PERMISSIONS_MASTER`, `MSTR_USER_ROLES`, `MSTR_USER_SCOPE`, `MSTR_USER_SITES`, `MSTR_AUDIT_LOG`, `MSTR_ALL_MODULES`, views `V_MY_PROFILE` / `VW_USER_ROLE_PERMISSIONS`.

---

## Resolved Decisions

1. **Build target = PostgreSQL `capa_assist`** (already created, reachable at `localhost:5433`). The live Oracle DB is **not** touched during the build.
2. **Faithful mirror, relevant subset.** Recreate only the Tier-1 + Tier-2 + Tier-4 tables (core CAPA + masters + the 3 `capa_ai_*` tables) in Postgres, using the **real Oracle table/column names**, **VARCHAR string IDs** (not SERIAL), and **TENANT_ID** scoping. Skip the Tier-5 auth/session/billing/APEX plumbing entirely.
3. **Repository/adapter layer.** All DB access goes through a `CapaRepository` interface. `PostgresCapaRepository` now; `OracleCapaRepository` later. Swap = add one class + set `DB_BACKEND=oracle`; agents/retrieval don't change. Post-swap, the Postgres implementation can be deleted as a single self-contained file.
4. **Seed = re-map what fits, drop the rest.** Re-map the reference's 40-CAPA domain content into the mirrored schema under one synthetic tenant (`CAPA_TENANT_ID=TENANT_ACERTECH`). Drop reference concepts with no home (assets/departments/employees). Add columns/tables only if genuinely needed.

## Type & Concept Mapping (Oracle → Postgres mirror)

| Oracle | Postgres (mirror) |
|---|---|
| `VARCHAR2(n)` | `VARCHAR(n)` |
| `CLOB` | `TEXT` |
| `NUMBER` (int-ish) / `NUMBER(p,s)` | `INTEGER`/`BIGINT` or `NUMERIC(p,s)` |
| `TIMESTAMP(6) WITH TIME ZONE` | `TIMESTAMPTZ` |
| `DATE` | `DATE` |
| `CHAR(1)` (Y/N flags) | `CHAR(1)` (kept as-is for fidelity) |
| `RAW(16)` | not in our subset (auth tables only) — skip |
| `SDO_GEOMETRY` (`MSTR_TENANT_SITES.LOCATION`) | dropped; keep `LATITUDE`/`LONGITUDE` `NUMERIC` |
| `BLOB` (evidence files) | dropped from mirror (not needed by AI service) |

Concept mappings that have no direct column:
- **Recurrence:** native `CAPA.IS_RECURRING` / `RECURRENCE_COUNT` / `LINKED_CAPA_IDS` (mirror them; no separate tracking table).
- **Effectiveness signal:** derive from `CAPA_REVIEWS.REVIEW_OUTCOME` + `CAPA_ACTIONS.VERIFIED_*` + `CAPA_CLOSURE.CLOSURE_STATUS`.
- **Root-cause category:** stored on `CAPA_RCA.ROOT_CAUSE_CATEGORY`, referencing the `CAPA_CATEGORIES` vocab (no native column in real Oracle).

## Config changes already applied (rolled back from the brief all-Oracle detour)

- `requirements.txt`: `psycopg2-binary` active; `oracledb` listed but commented (future adapter).
- `config.py`: Postgres config restored + `DB_BACKEND` flag (`postgres` now / `oracle` later), `CAPA_TENANT_ID`, pool sizing. Oracle config will be added when the Oracle adapter is built.
- `.env`: Postgres vars restored (`capa_assist`, `localhost:5433`), `DB_BACKEND=postgres`, `CAPA_TENANT_ID=TENANT_ACERTECH`, LLM keys kept.
- `repositories/` package created.

## Source → Mirror Mapping (reference seed → mirrored schema)

| Reference (old toy schema) | Mirror (real Oracle name) | Notes |
|---|---|---|
| `enterprise` (AcerTech) | `MSTR_TENANT_METADATA` | one tenant = `TENANT_ACERTECH` |
| `sites` | `MSTR_TENANT_SITES` | drop SDO geometry, keep `LATITUDE`/`LONGITUDE` |
| `departments` | `MSTR_TENANT_GROUPS` | no dept table → department becomes an owner group; `CAPA.OWNER_GROUP_ID` |
| `employees` | `MSTR_USERS_METADATA` | keyed by `USER_EMAIL`; role kept in `PROFILE`/meta |
| `assets` | — | **dropped** (no asset table; barely used in reference) |
| `root_cause_taxonomy` | `CAPA_CATEGORIES` | category controlled vocab |
| `capas` | `CAPA` | `source_type→SOURCE_MODULE`; `dept_id→OWNER_GROUP_ID`; severity/priority/status/type → `*_ID` FKs to masters |
| `capa_root_causes` (statement, rca_method) | `CAPA.ROOT_CAUSE` + `CAPA.RCA_METHOD_ID` + `CAPA_INVESTIGATIONS` | |
| `capa_root_causes` (contributing_factors, failed_controls, missing_controls, root_cause_category) | **`CAPA_RCA`** (new AI-side table) | `ROOT_CAUSE_CATEGORY` FK → `CAPA_CATEGORIES`; see "RCA table" below |
| `capa_actions` | `CAPA_ACTIONS` | `strength_label`/`effectiveness_result` → reviews/verify/closure (below) |
| `recurrence_tracking` | native `CAPA.IS_RECURRING` / `RECURRENCE_COUNT` / `LINKED_CAPA_IDS` | no separate table |

**RCA table (decided):** the reference's `contributing_factors` / `failed_controls` / `missing_controls` are high-value for the Generator/Evaluator (`analysis.md` flags `missing_controls` specifically) but have no column in the real Oracle schema — they'd come from a root-cause-analysis table that isn't set up in Oracle yet. We mirror them in a **new dedicated `CAPA_RCA` table** (FK to `CAPA`). It's an isolated AI-side extension: if the real system ultimately can't supply these fields, we drop `CAPA_RCA` and tune the agents — nothing else changes. Same isolate-the-removable-thing principle as the repository swap.

**Effectiveness derivation:** reference `strength_label` (Strong/Acceptable/Weak/Critical) + `effectiveness_result` (Pass/Fail/Pending) are seeded into `CAPA_REVIEWS.REVIEW_OUTCOME` + `CAPA_ACTIONS.VERIFIED_BY`/`VERIFIED_DATE` + `CAPA_CLOSURE.CLOSURE_STATUS`, so the derived effectiveness signal the agents read actually exists.

**Master values:** we mint our own master IDs/names (`SEV_HIGH`, `PRI_P1`, `STATUS_OPEN`, `TYPE_CORRECTIVE`, …) since we're not reading the real Oracle masters. The Oracle adapter will read the real master IDs later — our mirror's IDs are internal to the Postgres build and don't need to match.

---

## Sub-Phase 1a — Setup (schema + repository + contracts)

**1a.1 — Mirror DDL (`seeds/schema.sql`).** Postgres DDL recreating the relevant-subset tables with real Oracle names/columns, mapped types (see table above), `VARCHAR(50)` string IDs, `TENANT_ID` on every domain table, FKs, and `CHECK` constraints on controlled-vocab columns. Includes the new `CAPA_RCA` table + the 3 `capa_ai_*` tables. Idempotent (`CREATE TABLE IF NOT EXISTS`).

**1a.2 — Repository layer (`repositories/`).** `base.py` = `CapaRepository` abstract interface, methods named in domain terms (`fetch_capa`, `fetch_actions`, `fetch_rca`, `fetch_similar_capas`, `fetch_effective_actions`, `count_recurrence`, `write_evaluation`, `write_audit`, `save_context_package`, master lookups…). `postgres.py` = `PostgresCapaRepository` — the **only** place raw SQL lives; psycopg2 pool. `services/db.py` = factory returning the impl selected by `config.DB_BACKEND`.

**1a.3 — `models/schemas.py`.** Pydantic contracts mapped onto the mirrored schema; controlled-vocab fields typed as `Literal[...]` from the minted master values.

**Checkpoint 1a:** `schema.sql` applies clean to `capa_assist`; `PostgresCapaRepository` connects via the factory; a `capa_ai_*` write→read round-trips; `models/schemas.py` imports and a sample row validates. No raw SQL exists outside `repositories/postgres.py`.

## Sub-Phase 1b — Seeding (data + vector store)

**1b.1 — Extract (`seeds/data/*.json`).** One-time extraction of the 40 CAPAs + actions + root causes + master vocab from `reference/backend/seeds/*.sql` into structured JSON under `service/seeds/data/`. Makes `service/` self-contained (no seed-time dependency on read-only `reference/`).

**1b.2 — Loader (`seeds/load_seed.py`).** Reads the JSON, applies the mapping above, inserts in FK order (tenant → sites → groups → users → masters → CAPA → actions → RCA → investigations → reviews/closure). Idempotent (delete-by-`TENANT_ACERTECH` → insert), re-runnable. Seed SQL lives in `seeds/` (one-time setup tooling — exempt from the runtime "SQL only in the repository" rule); verification reads go through `PostgresCapaRepository`.

**1b.3 — Vector store (`seeds/seed_vector_db.py`).** ChromaDB collections seeded once: `historical_capas` (one doc per seeded action: root-cause + action text + derived effectiveness), `sop_documents` + `regulatory_documents` (reuse `reference/backend/data/sops` + `regulatory` files). Two-phase RAM strategy.

**Checkpoint 1b:** tenant-scoped `fetch_capa`/`fetch_actions` return seeded rows with master values resolved to names (not raw IDs); `fetch_similar_capas` filters by site/category; `fetch_rca` returns the controls fields; ChromaDB semantic search returns top-5; every returned row validates against `models/schemas.py`.

## Implementation / How to Run / How to Test

### Sub-Phase 1a — built, Checkpoint 1a passed

**`service/seeds/schema.sql`** — Postgres DDL for 28 tables: Tier 2 masters (`MSTR_TENANT_METADATA`, `MSTR_TENANT_SITES`, `MSTR_TENANT_GROUPS`, `MSTR_TENANT_SITE_GROUPS`, `MSTR_USERS_METADATA`, `MSTR_SEVERITY_MASTER`, `MSTR_PRIORITY_MASTER`, `MSTR_STATUS_MASTER`, `CAPA_STATUS_MASTER`, `CAPA_TYPE_MASTER`, `CAPA_CATEGORIES`, `CAPA_SUBCATEGORIES`, `CAPA_ESCALATION_LEVELS`, `CAPA_SLA_RULES`, `MSTR_HOLIDAY_CALENDAR`), Tier 1 core domain (`CAPA`, `CAPA_ACTIONS`, `CAPA_ACTION_PLAN`, `CAPA_INVESTIGATIONS`, `CAPA_REVIEWS`, `CAPA_REVIEW_HISTORY`, `CAPA_REVIEW_TASKS`, `CAPA_CLOSURE`, `CAPA_APPROVALS`), Tier 4 AI tables (`CAPA_RCA`, `capa_ai_evaluations`, `capa_ai_audit_trail`, `capa_ai_context_packages`). Real Oracle names/columns, `VARCHAR` string IDs, `TENANT_ID` scoping, FKs in dependency order. `BLOB`/`SDO_GEOMETRY` columns dropped per the type-mapping table; `MSTR_USERS_METADATA` also drops its auth-only columns (password hash/salt, MFA, lockout) since those are Tier-5-equivalent even though the table itself is Tier 2. `CREATE TABLE IF NOT EXISTS` throughout — confirmed idempotent by re-running.

**`service/repositories/base.py`** — `CapaRepository` ABC: domain-term methods (`fetch_capa`, `fetch_actions`, `fetch_rca`, `fetch_similar_capas`, `fetch_effective_actions`, `count_recurrence`, master lookups `fetch_severity`/`fetch_priority`/`fetch_status`/`fetch_capa_type`/`fetch_category`/`fetch_site`, and the 3 AI writers `write_evaluation`/`write_audit`/`save_context_package`). Every method is tenant-scoped and returns/accepts `models.schemas` Pydantic types only.

**`service/repositories/postgres.py`** — `PostgresCapaRepository(pool)`. The only file in the codebase containing raw SQL (confirmed via grep across `service/`). Uses `psycopg2.extras.RealDictCursor` + `Model.model_validate(row)` to map rows straight to Pydantic — no dict ever crosses back out of this file unvalidated.

**`service/services/db.py`** — `get_repository()` factory: lazily builds one `ThreadedConnectionPool` (sized from `config.DB_POOL_MIN/MAX`) and returns a cached `PostgresCapaRepository` when `config.DB_BACKEND == "postgres"`. Adding the Oracle backend later means one `elif` branch here + a new `repositories/oracle.py` — no other file changes.

**`service/models/schemas.py`** — one `OrmBase(BaseModel)` with `from_attributes=True`, then a Pydantic model per mirrored table (Tier 1 + Tier 2 + Tier 4), field names matching the SQL columns lowercase. Controlled-vocab fields (severity name, priority level, status, capa type) are `str` for now, not `Literal[...]` — the master vocab isn't minted until seed extraction (1b.1), so locking the literal set now would be guessing. Revisit once 1b values exist.

### How to Run

```bash
conda activate capa-ai
cd service
psql -h localhost -p 5433 -U postgres -d capa_assist -f seeds/schema.sql   # apply/reapply DDL (idempotent)
python -c "from services.db import get_repository; print(type(get_repository()).__name__)"
```

### How to Test (Checkpoint 1a — passed)

Manual verification script (inserted minimal tenant/site/group/masters/CAPA/action rows to satisfy FKs, exercised every repository method, then deleted them):

1. `schema.sql` applied clean (28 `CREATE TABLE`), re-run produced only `NOTICE: relation already exists, skipping` — idempotent confirmed.
2. `get_repository()` returns `PostgresCapaRepository` (factory resolves `DB_BACKEND=postgres`).
3. `fetch_capa("T_CHK", "CAPA_CHK")` and `fetch_actions(...)` returned validated `Capa`/`CapaAction` instances with correct field values.
4. Write→read round-trip on all 3 AI tables: `write_audit` → row readable with correct `agent`/`input_payload` (JSONB survives round-trip); `write_evaluation` → `score`/`weakness_level`/`dimension_results` readable; `save_context_package` → `package_payload` readable.
5. `grep -rn "SELECT\|INSERT INTO\|UPDATE \|DELETE FROM" service/*.py` (recursive) → only matches in `repositories/postgres.py`. No raw SQL leaked into agents/services/api.

Real `tests/integration/test_postgres_repository.py` (pytest, hitting the live `capa_assist` dev DB) is deferred to right before 1b, once seed data exists to assert against instead of throwaway rows.

### Sub-Phase 1b — built, Checkpoint 1b passed

**`service/seeds/build_seed_data.py`** — one-time extraction script, verbatim-transcribed source data from `reference/backend/seeds/*.sql` (`ENTERPRISE`, `SITES_SRC` 11, `DEPARTMENTS_SRC` 64, `EMPLOYEES_SRC` 249, `ROOT_CAUSE_TAXONOMY_SRC` 8, `CAPAS_SRC` 40, `ROOT_CAUSES_SRC` 40, `ACTIONS_SRC` 58), mapping dicts, recurrence cluster data, transform functions, and a `main()` that writes 17 JSON files to `seeds/data/`. Run once: `python seeds/build_seed_data.py`.

**Mapping / derivation rules actually used** (the master-ID minting and derivation decisions, since no real Oracle masters exist to read):

| Source concept | Mirror | Rule |
|---|---|---|
| `capas.severity`/`priority` | `SEV_*`/`PRI_*` IDs | `SEVERITY_MAP`/`PRIORITY_MAP` — 5 minted values each, severity also carries a numeric `severity_level` 1–5 |
| `capas.status` | `STATUS_*` IDs in `CAPA_STATUS_MASTER` (`SOURCE_TABLE='CAPA'`) | `STATUS_MAP` |
| `capa_actions.*` status | `ACTION_STATUS_*` IDs (`SOURCE_TABLE='CAPA_ACTIONS'`) | No per-action status column exists in the real schema — **derived from the parent CAPA's status** via `ACTION_STATUS_MAP` |
| `capas.capa_type`/`capa_actions.action_type` | `TYPE_*` IDs in `CAPA_TYPE_MASTER` | `CAPA_TYPE_MAP` — 4 minted types (Containment/Corrective/Preventive/Risk Mitigation). The composite label `"Corrective and Preventive"` has no single FK target (`CAPA.CAPA_TYPE_ID` is singular) — collapsed to `TYPE_CORRECTIVE` |
| `root_cause_taxonomy.category_name` | `CAT_*` IDs in `CAPA_CATEGORIES` | `CATEGORY_MAP` — all 8 taxonomy entries map 1:1, `CREATED_BY` = enterprise contact email |
| tenant/site/group/user `STATUS_ID` | `STATUS_ACTIVE` | Single shared row minted in `MSTR_STATUS_MASTER` (generic/tenant-agnostic, no FK constraint ties these columns to it — just needed *a* value) |
| `capa_root_causes.rca_method` | `RCA_METHOD_*` IDs | `RCA_METHOD_MAP` — not a real master table (`CAPA.RCA_METHOD_ID` has no FK constraint), minted for readability only |
| Recurrence (`capas` 1, 26–30 and 31–35) | `CAPA.IS_RECURRING`/`RECURRENCE_COUNT`/`LINKED_CAPA_IDS` | `RECURRENCE_CLUSTERS` — `RECURRENCE_COUNT` = number of *prior* occurrences linked at that point (Cluster A: 1→0, 26→1, 27→2, 28→3, 29→4, 30→5; Cluster B: 31→0, 32→1, 33→2, 34→3, 35→4), `LINKED_CAPA_IDS` = comma-joined prior CAPA IDs |
| `capa_root_causes` (statement, rca_method) | `CAPA.ROOT_CAUSE` + `CAPA.RCA_METHOD_ID` | Per the Source → Mirror Mapping above |
| `capa_root_causes` (contributing/failed/missing controls, category) | `CAPA_RCA` | 1:1, `NULL` → `[]` coercion |
| Investigations (40, 1 per CAPA) | `CAPA_INVESTIGATIONS` | `INVESTIGATION_DESCRIPTION` = root cause statement; `INVESTIGATION_OUTCOME` = `"Direct Cause Identified"` if `rca_method == "Incident Report Review"` else `"Root Cause Confirmed"`; `INVESTIGATOR_EMAIL` = parent CAPA's `CREATED_BY` |
| Reviews (58, 1 per action) | `CAPA_REVIEWS` | `REVIEW_OUTCOME` via `REVIEW_OUTCOME_MAP` (Pass→Effective, Fail→Ineffective, Pending→Pending Review); `REVIEWER_COMMENTS` = action's `effectiveness_check` text; `REVIEW_DATE` = `effectiveness_verified_at`; `REVIEWED_BY` = parent CAPA's `ASSIGNED_TO`. **Note:** `CAPA_REVIEWS` has no `ACTION_ID` column in the real schema — it's CAPA-scoped, not action-scoped, so a CAPA with 2 actions gets 2 review rows that both FK to the same `CAPA_ID` |
| Action priority/severity | inherited from parent CAPA | `capa_actions` has no own severity/priority in the source; `action_type` (own field) drives `CAPA_TYPE_ID`, but `PRIORITY_ID`/`SEVERITY_ID` inherit the parent CAPA's |
| Action verification | `CAPA_ACTIONS.VERIFIED_BY`/`VERIFIED_DATE` | Set when `effectiveness_result` ∈ {Pass, Fail} (i.e. a verification actually happened — `Pending` means not yet verified) |
| Closures (29, 1 per `Closed` CAPA) | `CAPA_CLOSURE` | `CLOSURE_STATUS` = `"Verified Effective"` if every action's `effectiveness_result == "Pass"`, `"Closed - Ineffective"` if any `"Fail"`, else `"Closed"`. `COMMENTED_BY`/`COMMENTED_DATE` are extra JSON keys not on the `CapaClosure` Pydantic model (that model predates noticing these are `NOT NULL` in `schema.sql`) — the loader inserts them straight from JSON via raw SQL since `seeds/` is exempt from the "SQL only in the repository" rule |

**`service/seeds/load_seed.py`** — FK-ordered idempotent loader. Deletes any existing `TENANT_ACERTECH` rows (reverse FK order; `MSTR_SEVERITY_MASTER`/`MSTR_PRIORITY_MASTER` are tenant-agnostic globals, deleted by the `SEV_%`/`PRI_%` ID prefix instead) then inserts: `MSTR_STATUS_MASTER` → tenant → sites → groups → site_groups → users → severities → priorities → capa_statuses → capa_types → categories → CAPA → CAPA_ACTIONS → CAPA_RCA → CAPA_INVESTIGATIONS → CAPA_REVIEWS → CAPA_CLOSURE. Raw SQL (seed-tooling exemption); reads `config.DATABASE_URL`/`config.CAPA_TENANT_ID` directly via `psycopg2.connect`, not through `get_repository()` (the loader writes, the repository's job is reads/validated writes for runtime agents).

**`service/seeds/seed_vector_db.py`** — two-phase RAM strategy (embed with fastembed → release model → open ChromaDB → insert pre-computed embeddings), same pattern as `reference/backend/seeds/seed_vector_db.py`. `historical_capas` joins `CAPA_ACTIONS`/`CAPA`/`CAPA_RCA`/`CAPA_CATEGORIES`/masters (no join to `CAPA_REVIEWS` — see the "Reviews" row above for why that would fan out per-action); `sop_documents`/`regulatory_documents` embed the 25 SOP + 22 regulatory `.txt` files, copied from `reference/backend/data/` into `service/data/{sops,regulatory}/` so `service/` has no seed-time read dependency on `reference/`. Added `config.EMBEDDING_FN` (lazy-loaded fastembed `BAAI/bge-small-en-v1.5` wrapped as a `chromadb.EmbeddingFunction`) and confirmed `config.EMBEDDING_MODEL_NAME` — both were deferred from Phase 0, needed now for collection creation. Run per-collection (`--collection historical_capas|sop_documents|regulatory_documents|all`) or `--smoke-test`.

### How to Run (Sub-Phase 1b)

```bash
conda activate capa-ai
cd service
python seeds/build_seed_data.py                          # (re)generate seeds/data/*.json from source
python seeds/load_seed.py                                 # load into capa_assist (idempotent)
python seeds/seed_vector_db.py --collection historical_capas
python seeds/seed_vector_db.py --collection sop_documents
python seeds/seed_vector_db.py --collection regulatory_documents
python seeds/seed_vector_db.py --smoke-test
```

### How to Test (Checkpoint 1b — passed)

1. **Seed counts** — `build_seed_data.py` wrote: 1 tenant, 11 sites, 64 groups, 64 site_groups, 249 users, 5 severities, 5 priorities, 8 capa_statuses, 4 capa_types, 8 categories, 1 generic status, 40 CAPAs, 58 actions, 40 RCA rows, 40 investigations, 58 reviews, 29 closures (29 = count of `Closed`-status CAPAs in the 40).
2. `fetch_capa("TENANT_ACERTECH", "CAPA_0001")` returns a valid `Capa`; `fetch_severity`/`fetch_priority`/`fetch_status`/`fetch_capa_type` resolve its IDs to names (`High`/`High`/`Closed`/`Corrective`) — master values resolve, not just raw IDs.
3. `fetch_actions("TENANT_ACERTECH", "CAPA_0001")` returns 2 validated `CapaAction` rows.
4. `fetch_similar_capas("TENANT_ACERTECH", site_id="SITE_05", category_id="CAT_TRAINING_GAP")` returns exactly `{CAPA_0007, CAPA_0031..0035}` — confirms site + category filtering both work correctly (CAPA 7 and Cluster B are the only site-5/Training-Gap CAPAs).
5. `fetch_rca("TENANT_ACERTECH", "CAPA_0030")` returns a validated `CapaRCA` with non-empty `missing_controls`.
6. `count_recurrence`/`fetch_capa` on `CAPA_0030` confirm the recurrence chain: `recurrence_count=5`, `is_recurring=1`, `linked_capa_ids="CAPA_0001,CAPA_0026,CAPA_0027,CAPA_0028,CAPA_0029"`.
7. ChromaDB: `historical_capas` (58 docs), `sop_documents` (25 docs), `regulatory_documents` (22 docs) all populated; semantic `query_texts` smoke test returns sensible top-5 (e.g. "wire rope failure on overhead crane recurring" → 4 of 5 hits are Cluster A actions).
8. Every row returned by every repository method above validates against `models/schemas.py` by construction (`PostgresCapaRepository` uses `Model.model_validate(row)` — an invalid row would raise, not silently pass).

Real `tests/integration/test_postgres_repository.py` (pytest, asserting the above programmatically against the live seeded `capa_assist` DB) was deferred at checkpoint time; it is now **built** — see "Phase 1 Wrap-Up" below.

---

## Phase 1 Wrap-Up (before Phase 2)

A closing pass to finish loose ends flagged during a schema/seed review, so Phase 2 builds on complete, tested ground.

### 1. Master/lookup description fills

Several description columns existed in `schema.sql` but were left `NULL` in the first seed pass. Filled now because the Context Retrieval Agent should inject human-readable *meaning* per master value (what "High severity" / "Corrective" / "Training Gap" actually mean), not bare IDs. All changes are seed-data + model only — **no DDL change** (columns already existed):

| Column filled | Source (new in `build_seed_data.py`) | Notes |
|---|---|---|
| `MSTR_SEVERITY_MASTER.DESCRIPTION` | `SEVERITY_DESC` (5) | generic, tenant-agnostic severity semantics |
| `MSTR_PRIORITY_MASTER.DESCRIPTION` | `PRIORITY_DESC` (5) | generic priority/handling semantics |
| `CAPA_TYPE_MASTER.CAPA_TYPE_DESCRIPTION` | `CAPA_TYPE_DESC` (4, keyed by minted type ID) | defines Containment/Corrective/Preventive/Risk Mitigation |
| `CAPA_CATEGORIES.CATEGORY_DESCRIPTION` | `CATEGORY_DESC` (8) | defines each root-cause taxonomy term |
| `MSTR_TENANT_SITES.META` | `SITE_DESC` (11, keyed by site number) | per-site free-text context (hazard profile / function) |

**Site description decision:** the real Oracle `MSTR_TENANT_SITES` has no `SITE_DESCRIPTION` column but does have `META` — so the per-site blurb goes in `META` rather than adding a non-faithful column. `META` is the schema-faithful home for free-text site context.

Wiring touched: `build_seed_data.py` (`build_sites`, `build_masters`), `load_seed.py` (5 INSERTs extended to carry the new columns), `models/schemas.py` (added `Severity.description`, `Priority.description`, `Site.meta` — `CapaType.capa_type_description`/`Category.category_description` already existed). All `Optional[str] = None` so the models stay backward-compatible. Descriptions confirmed surfacing through `PostgresCapaRepository` master lookups (which `SELECT *`).

### 2. Recurrence — ownership clarified (no code change)

Confirmed for the record (drove a Phase 2 design note): `CAPA.RECURRENCE_COUNT`/`IS_RECURRING`/`LINKED_CAPA_IDS` are **native** real-Oracle columns, not AI-side additions. In the seed they are **pre-baked** via `RECURRENCE_CLUSTERS` (test fixtures), not detected. At runtime, recurrence *retrieval/measurement* (count, linked IDs, category) belongs to the **Context Retrieval Agent**; recurrence *judgment* (is this a repeat of a previously-failed fix → penalty) belongs to the **Evaluator** (reference Layer 3). The ContextPackage designed in Phase 2 must carry `recurrence_count` + `linked_capa_ids` + `root_cause_category` + effective-action data so the Evaluator isn't starved (this exact wiring gap made recurrence 100% dead in the reference — `analysis.md` finding). AI never auto-writes these fields (human-in-the-loop).

### 3. Formalized integration pytest

`tests/integration/test_postgres_repository.py` (+ `tests/integration/conftest.py`) — 13 tests, the Checkpoint 1b manual verification turned into pytest, plus assertions on the new description/META fills, plus AI-table write→read round-trips. Asserts against the fixed 40-CAPA seed, so it doubles as a seed-loader regression guard. Self-skips (not fails) if the dev DB is unreachable. **All 13 pass.**

### 4. Data characteristics noted (for the Phase 2 Context Agent)

Findings from a seed review — not bugs, but things the Context Retrieval Agent design should know so it doesn't rediscover them:

- **`CAPA_RCA` is sparse by design.** 18 of 40 RCA rows have empty `contributing_factors`/`failed_controls`/`missing_controls` (`[]`, not `""`) — the reference only supplied structured controls for the richer/recurrence CAPAs; the loader coerces `NULL → []`. `root_cause_category` is populated on all 40. These thin-RCA cases are realistic **weak-CAPA test fixtures** (incomplete RCA = a weakness signal the Evaluator should catch) — keep them, don't backfill.
- **`CAPA_INVESTIGATIONS` largely duplicates `CAPA`.** By seed mapping, `INVESTIGATION_DESCRIPTION` == `CAPA.ROOT_CAUSE` (verbatim) and `INVESTIGATION_TITLE` == `"Root Cause Investigation — " + CAPA_TITLE`. The reference had no distinct investigation narrative. So the investigations table adds little signal beyond `CAPA.ROOT_CAUSE` for now — the Context Agent can treat it as redundant / skip it unless richer distinct text is seeded later.
- **`CAPA_REVIEWS` is the effectiveness signal, and is CAPA-scoped not action-scoped.** Purpose: post-action reviewer verdict (`REVIEW_OUTCOME` ∈ Effective/Ineffective/Pending Review, derived from the reference's Pass/Fail/Pending) — this is how the Evaluator learns whether an action type historically worked. The real `CAPA_REVIEWS` has no `ACTION_ID` column, so a CAPA with 2 actions has 2 review rows both FK'd to the same `CAPA_ID` (1 review per source action, but keyed by CAPA). Effectiveness for a *specific* action is therefore reconstructed from `CAPA_ACTIONS.VERIFIED_BY`/`VERIFIED_DATE` + `CAPA_CLOSURE.CLOSURE_STATUS`, not from a per-action review row.

### How to Run / Test (Wrap-Up)

```bash
conda activate capa-ai
cd service
python seeds/build_seed_data.py        # regenerate JSON (now includes descriptions/META)
python seeds/load_seed.py              # reload (idempotent)
pytest tests/integration/test_postgres_repository.py -v   # 13 tests, all pass
```
