# Phase 2 — Context Retrieval Agent

**Status: PHASE 2 COMPLETE, including Sub-Phase 2b hardening pass.** All checkpoint tests pass against the live `capa_assist` DB, seeded ChromaDB, and live Groq LLM. 50/50 tests pass (39 original + 11 from 2b).

**Retrofit (Phase 3):** `POST /capa/context` added in `api/routes.py` — a thin wrapper exposing `get_context_package()` directly. Starting Phase 3, API routes ship per-phase instead of all arriving at the dedicated Orchestrator/API phase (see `phases/phase3.md` decision 3); this endpoint was added then, not during this phase's original build.

This is the most important agent in the system (per `reference/overview.md` 3.3) — every downstream agent's output quality is bounded by the quality of the context this agent produces. Built and hardened first, to a high standard, before Generator/Evaluator/Improver/Explainability.

---

## Goal

Given a `CAPARecord`, produce a validated `ContextPackage`: `normalize()` (pure Python) → `enrich()` (LLM, only if inference needed) → `retrieve()` (asyncio-parallel, selective per downstream agent) → assembled, deduplicated, schema-valid output.

---

## Decisions made this session

### 1. NL2SQL scope — new `MSTR_TENANT_EMP` table

Reference design used NL2SQL for live employee/asset lookups. Phase 1 dropped assets and departments entirely (no home in the real schema). Employees, however, are wanted back — **not** as a new "department" concept, but as a genuine employee-directory table the real Oracle schema is assumed to have (not present in the `schema.csv` dump we were given, but the user confirmed it exists in production and asked us to assume its shape). Named `MSTR_TENANT_EMP` (Tier 2, mirrors the `MSTR_TENANT_*` naming convention).

Distinct from `MSTR_USERS_METADATA` (already seeded from the same 249-employee source, but only carries login-identity fields: email/name/group/status — no role). `MSTR_TENANT_EMP` is the HR/org-directory record: role title + role description + site + group(dept-equivalent), optionally linked to a `MSTR_USERS_METADATA` row via `USER_EMAIL`. This split mirrors real systems (auth identity vs. org-chart data) and lets NL2SQL answer role-based questions ("who is the EHS officer at Site X") that the current `users` table can't.

**Assumed schema** (documented here since no source dump exists for it):
```sql
MSTR_TENANT_EMP (
    EMP_ID            VARCHAR(50)  PRIMARY KEY,
    TENANT_ID         VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_METADATA,
    SITE_ID           VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_SITES,
    GROUP_ID          VARCHAR(50)  NOT NULL REFERENCES MSTR_TENANT_GROUPS,
    USER_EMAIL        VARCHAR(320) REFERENCES MSTR_USERS_METADATA(USER_EMAIL),
    FULL_NAME         VARCHAR(150) NOT NULL,
    ROLE_TITLE        VARCHAR(100),
    ROLE_DESCRIPTION  TEXT,
    STATUS_ID         VARCHAR(50)  NOT NULL,
    CREATED_DATE      TIMESTAMPTZ  DEFAULT now()
)
```

**Seed source:** `reference/backend/seeds/seed_employees.sql` (249 employees, full role/role_description text) — richer than what `build_seed_data.py` currently transcribes (`EMPLOYEES_SRC` today only carries emp_id/dept_id/name/email, role was dropped). Extend `EMPLOYEES_SRC` to include role + role_description + is_active, add `build_employees()`, map `dept_id → GROUP_ID` using the existing `_group_id()` helper (same mapping `build_groups()`/`build_users()` already use) and `dept_id → SITE_ID` via existing `DEPT_SITE`.

### 2. NL2SQL design — guarded, narrow-scope, separate exemption from the repository rule

NL2SQL is LLM-generated SQL against live tables — fundamentally different from the repository layer's fixed, parameterized methods, so it can't be forced through `CapaRepository`. Treat it like the seed-loader: **a second, explicit, documented exemption** to "raw SQL only in `repositories/postgres.py`" (CLAUDE.md's rule predates this — flagging it here per rule 10's spirit of surfacing architectural calls).

Guardrails (mirroring the reference's hardened NL2SQL, per `reference/CLAUDE.md`'s Phase 6 notes — "NL2SQL guard rejects UNION/CTE/multi-statement queries"):
- Whitelist of queryable tables only: `CAPA`, `CAPA_ACTIONS`, `MSTR_TENANT_EMP`, plus the Tier-2 masters. No `capa_ai_*` tables, no write verbs.
- Single `SELECT` statement only — reject multi-statement (`;`), `UNION`, CTEs (`WITH`), DDL/DML verbs, comments-as-injection.
- Enforce `LIMIT` if the LLM omits one.
- Always `TENANT_ID = :tenant_id` injected/verified, never trusted from the LLM output.
- Runs against `config.NL2SQL_DATABASE_URL` — dedicated read-only Postgres role (`capa_ai_readonly`), falls back to `DATABASE_URL` if unset (matches existing `config.py` comment). **Will create this role** (`seeds/seed_readonly_role.sql`, `GRANT SELECT` only on the whitelisted tables) — a DB-level change, will confirm before running.

### 3. RETRIEVAL_CONFIG restored to original 5-system shape

```python
RETRIEVAL_CONFIG = {
    "generator":      ["sql", "vector", "nl2sql", "sop", "regulatory"],
    "evaluator":      ["sql", "vector", "nl2sql"],
    "improver":       ["sql", "vector"],
    "explainability": [],
}
```

---

## Build plan

### 2a — Employee data (extends Phase 1 seed, scoped here since it exists only to feed NL2SQL)
- `seeds/schema.sql` — add `MSTR_TENANT_EMP` DDL (idempotent, as above)
- `seeds/seed_readonly_role.sql` — `capa_ai_readonly` role, `SELECT`-only grants on the NL2SQL whitelist
- `seeds/build_seed_data.py` — extend `EMPLOYEES_SRC` with role/role_description/is_active from `reference/backend/seeds/seed_employees.sql`; add `build_employees()`
- `seeds/load_seed.py` — insert `MSTR_TENANT_EMP` rows (FK-ordered, after groups/sites/users)
- `models/schemas.py` — add `Employee`
- `repositories/base.py` + `postgres.py` — add `fetch_employees(tenant_id, site_id=None, group_id=None, role_title=None)` (direct lookup path, separate from NL2SQL's free-form path)

### 2b — LLM service (needed by `enrich()` and NL2SQL)
- `services/llm.py` — `call_llm()` / `call_llm_json()`, Groq (key rotation, 4 keys present) → OpenRouter (4 keys present) → Ollama (not configured locally — tier skipped gracefully, not hard-required). Raw `httpx`, no LangChain, matching `reference/backend/services/llm.py` pattern.

### 2c — Schemas
- `models/schemas.py` — `CAPARecord` (entry payload), `ContextPackage` + submodels: `SimilarCapaSummary`, `EffectiveActionSummary`, `SopExcerpt`, `RegulatoryExcerpt`, `InferredField` (value + `source: Literal["inferred"]` + `confidence: float`), `missing_fields: list[str]`. No raw dicts.

### 2d — Retrieval modules
- `retrieval/normalize.py` — pure Python, `CAPARecord` → normalized fields + `missing_fields`. No LLM.
- `retrieval/enrich.py` — LLM call only if a gap is fillable (e.g. severity inferred from `source_module`). Every inferred value tagged `source`+`confidence`. No call at all if nothing to infer.
- `retrieval/sql_retrieval.py` — wraps `fetch_similar_capas` / `fetch_effective_actions` / `count_recurrence`, tenant-scoped, via the repository (no raw SQL here).
- `retrieval/nl2sql.py` — guarded LLM→SQL path described above.
- `retrieval/vector_retrieval.py` — Chroma semantic search across `historical_capas` / `sop_documents` / `regulatory_documents`.
- `retrieval/context_retrieval.py` — orchestrates `normalize → enrich → retrieve` (asyncio, selective via `RETRIEVAL_CONFIG[agent_name]`), dedups `similar_capas` by `capa_id`, merges SQL+vector metadata for the same record, returns validated `ContextPackage`.

### 2e — Tests
10 varied `CAPARecord` inputs (complete / missing severity / missing group / Incident source / Audit source), asserting: valid `ContextPackage`; `missing_fields` correct; `similar_capas` deduplicated; inferred fields tagged with confidence; ≥1 result per configured system when data exists; `explainability` config → empty retrieval, no queries run.

---

## Checkpoint 2 — PASSED

- `MSTR_TENANT_EMP` seeded (249 rows), `fetch_employees` resolves role/site/group correctly
- NL2SQL guard rejects a deliberately malicious prompt-injected query (UNION/multi-statement attempt) in a dedicated test
- 10/10 `ContextPackage` tests pass per above
- `grep` for raw SQL outside `repositories/postgres.py` shows only `seeds/` (loader) and `retrieval/nl2sql.py` (documented exemption) as the two allowed exceptions

---

## Implementation

**`seeds/schema.sql`** — added `MSTR_TENANT_EMP` (assumed schema, see decision 1), FKs to tenant/site/group/`MSTR_USERS_METADATA(USER_EMAIL)`. Applied clean to live `capa_assist`.

**`seeds/seed_readonly_role.sql`** — `capa_ai_readonly` Postgres role, `SELECT`-only grants on the 18-table NL2SQL whitelist (no `capa_ai_*` tables). Created live; credentials in `.env` as `NL2SQL_DATABASE_URL`.

**`seeds/build_seed_data.py`** — `EMPLOYEES_SRC` extended from a 4-tuple (`emp_id, dept_id, name, email`) to a 6-tuple adding `role`/`role_description`, parsed programmatically from `reference/backend/seeds/seed_employees.sql` (249 rows, regex-extracted, not hand-retyped — avoids transcription error on free-text role descriptions). Added `build_employees()` mapping `dept_id → GROUP_ID`/`SITE_ID` via the existing `_group_id()`/`DEPT_SITE` helpers (same mapping `build_groups()`/`build_users()` already use). `EMP_EMAIL`/`DEPT_FIRST_EMP`/`build_users()` unpacking updated for the new tuple shape.

**`seeds/load_seed.py`** — `MSTR_TENANT_EMP` insert added (after users, since it FKs to `MSTR_USERS_METADATA`); added to the idempotent delete-order list.

**`models/schemas.py`** — `Employee` (Tier 2 mirror model); Phase 2 agent-facing contracts: `CAPARecord`, `ContextPackage`, `SimilarCapaSummary`, `EffectiveActionSummary`, `SopExcerpt`, `RegulatoryExcerpt`, `InferredField`, `NL2SQLResult`, `AgentInput`. `SourceModule`/`SeverityLevel`/`ActionType` literals confirmed against the actual minted master vocab in `seeds/data/*.json` (exact match to the reference's literal sets). `enterprise_context` is `list[NL2SQLResult]`, not a raw dict — the one documented exception is `NL2SQLResult.rows: list[dict]` itself, since free-form NL2SQL output shape genuinely varies with whatever whitelisted SELECT the LLM wrote.

**`repositories/base.py` + `postgres.py`** — added `fetch_employees(tenant_id, site_id=, group_id=, role_title=)`, the direct-lookup path (distinct from NL2SQL's free-form path over the same table).

**`config.py`** — `RETRIEVAL_CONFIG` (5-system shape per agent, restored from the original design once `MSTR_TENANT_EMP` made NL2SQL meaningful again); `GROQ_TO_OR_MODEL`/`GROQ_TO_OLLAMA_MODEL`/`ACTIVE_BASE_URL` (ported from reference, needed by `services/llm.py`).

**`services/llm.py`** — `call_llm()`/`call_llm_json()`, ported from `reference/backend/services/llm.py` near-verbatim (3-tier fallback: Groq key rotation → OpenRouter key rotation → Ollama auto-start; schema-validation retry with correction prompt; truncation retry with bumped `max_tokens`). One change: Ollama tier fails fast with a clear error if `ollama` isn't installed, instead of assuming it's always available — this environment has no local Ollama configured.

**`retrieval/normalize.py`** — pure Python. `CAPARecord.model_dump()` + a tracked-fields list (`site_id`, `owner_group_id`, `severity`, `priority`, `due_date`, `capa_type`, `root_cause_statement`, `root_cause_category`) → `missing_fields`.

**`retrieval/enrich.py`** — LLM call (`LIGHT_MODEL`) only when `severity` and/or `capa_type` are in `missing_fields` (the two fields we know how to infer reliably from title/description/source_module). Returns `{}` with zero LLM calls otherwise. **Hardening note from live testing:** the first prompt draft included "leave the other null" (for when only one field was missing) — `llama-3.1-8b-instant` misread this as "null out everything" and returned all-null on a case where *both* fields were actually needed. Fixed by dropping that clause entirely (the caller already filters to `needed` fields, so the instruction was redundant and actively harmful).

**`retrieval/sql_retrieval.py`** — wraps `fetch_similar_capas`/`fetch_effective_actions`/`count_recurrence` through the repository (no raw SQL), joining in `fetch_actions`/`fetch_rca`/`fetch_capa_type` per result to build fully-typed `SimilarCapaSummary`/`EffectiveActionSummary` objects.

**`retrieval/vector_retrieval.py`** — semantic search over the 3 Phase-1-seeded ChromaDB collections. Client constructed behind a `threading.Lock` (the reference's Phase 6 hardening found the lazy ChromaDB client singleton wasn't thread-safe under concurrent retrieval — same fix ported here from the start instead of waiting to rediscover it).

**Known gap — new-CAPA embedding (deferred, not a Phase 2 blocker):** `historical_capas` only has the 58 seeded actions; nothing in the runtime path embeds a newly created/closed/verified real CAPA action into it, so the vector store goes stale once real traffic exists. Decided: a standalone embedding-sync service, built **after the last build phase** (post-Phase 5), that finds CAPAs/actions missing from `historical_capas` and embeds+upserts them incrementally — not a retrieval-time concern, so it doesn't block Phase 2/3/4. Tracked in `phases/production.md`.

**`retrieval/nl2sql.py`** — guarded LLM→SQL path. `_guard()` enforces: single `SELECT` only, no UNION/CTE/DDL/DML/comment-injection, only whitelisted tables referenced, mandatory `tenant_id = %(tenant_id)s` placeholder (verified by regex, value always passed as a bound psycopg2 param — never string-interpolated), auto-appended `LIMIT` if the model omitted one, and `%`-escaping of any literal percent signs the model writes into string literals (e.g. `ILIKE '%foo%'`) so they don't collide with psycopg2's own param-substitution syntax — found via live testing (`argument formats can't be mixed`), not anticipated upfront. `_SCHEMA_DESCRIPTION` constant gives the LLM real column names per whitelisted table — without it, the model hallucinated plausible-but-wrong columns (`ehs_officer_id`, `first_name`/`last_name`) even though table-name-only prompting passed every guard check. Runs against `NL2SQL_DATABASE_URL` (`capa_ai_readonly`) with a 5s `statement_timeout`. Guard/LLM/DB failures all degrade to an empty `NL2SQLResult` rather than raising.

**`retrieval/context_retrieval.py`** — orchestrates `normalize → enrich → retrieve`. Retrieve runs all configured systems concurrently (`asyncio.gather`; sync repo/Chroma calls wrapped in `asyncio.to_thread` so they don't block the event loop alongside the async `nl2sql`/LLM calls). `similar_capas` deduplicated by `capa_id` — SQL's structural match wins over vector's semantic match on a collision (richer metadata). NL2SQL is skipped (not attempted) when `site_id` is absent, since the one wired NL2SQL question (`"List employees and their roles at site {site_id}"`) has nothing to filter on.

## How to Run

```bash
conda activate capa-ai
cd service
psql -h localhost -p 5433 -U postgres -d capa_assist -f seeds/schema.sql            # adds MSTR_TENANT_EMP (idempotent)
psql -h localhost -p 5433 -U postgres -d capa_assist -f seeds/seed_readonly_role.sql # capa_ai_readonly role (idempotent)
python seeds/build_seed_data.py    # regenerate JSON, now includes employees.json
python seeds/load_seed.py          # reload (idempotent)
```

## How to Test (Checkpoint 2 — passed)

```bash
pytest tests/unit/test_nl2sql_guard.py -v                  # 16 tests, pure guard logic, no network
pytest tests/integration/test_context_retrieval.py -v       # 10 tests, live DB + ChromaDB + Groq
```

1. `MSTR_TENANT_EMP`: 249 rows; `fetch_employees('TENANT_ACERTECH', role_title='EHS Officer')` → 10 rows across sites; FK joins to site/group/user resolve correctly.
2. `services/llm.py`: live `call_llm()` round-trip confirmed against real Groq.
3. `retrieval/enrich.py`: live LLM correctly infers `severity=High`/`capa_type=Corrective` (with confidence) from a forklift-collision-fracture description; returns `{}` with zero LLM calls when nothing is inferable.
4. `retrieval/sql_retrieval.py`: `fetch_similar_capas(site_id="SITE_05", category_id="CAT_TRAINING_GAP")` → the same 6-CAPA set Phase 1 confirmed; `count_recurrence("CAPA_0030")` → 5, matching Phase 1.
5. `retrieval/vector_retrieval.py`: "wire rope failure on overhead crane recurring" → top-5 includes `CAPA_0001`/`CAPA_0029`/`CAPA_0030` (Cluster A), matching Phase 1's smoke test.
6. `retrieval/nl2sql.py` guard: 16/16 unit tests — rejects multi-statement, UNION, CTE, non-whitelisted table, missing tenant filter, literal tenant value (not the bound placeholder), DDL/DML, `pg_sleep`; accepts well-formed whitelisted queries; correctly appends `LIMIT`; correctly escapes literal `%` without breaking the tenant placeholder. Live: "Who is the EHS Officer at site SITE_01?" → correct guarded SQL → `Priya Nair` (matches `fetch_employees` result for the same role/site).
7. `retrieval/context_retrieval.py`: 10/10 `ContextPackage` checkpoint tests — `generator`/`evaluator`/`improver` configs all populate the systems they're configured for (verified live, e.g. `generator` on a complete input returned 6 deduplicated `similar_capas`, 20 `effective_actions`, 5 SOPs, 5 regulatory excerpts, 29-row `enterprise_context`, in ~1.5s for all 5 systems run concurrently); `missing_fields` correct on every partial-input case; `inferred_fields` always carry `source="inferred"` + a 0–1 confidence; `explainability` config returns every retrieval list empty (no queries run) in ~0.4s (just the `enrich()` LLM call on that test's missing fields).
8. `grep -rln "SELECT \|INSERT INTO\|UPDATE \|DELETE FROM" --include="*.py" .` → `repositories/postgres.py` (runtime), `seeds/load_seed.py` (seed-tooling exemption), `retrieval/nl2sql.py` (documented Phase 2 exemption, guarded as above), plus two harmless false positives (`models/schemas.py` has the word "SELECT" in a comment; `tests/*` have SQL keywords inside test-fixture strings, not executable application SQL).

---

## Sub-Phase 2b — Hardening pass (before Phase 3)

A code-review pass surfaced 6 real gaps in the Phase 2 implementation — confirmed valid on inspection, not false alarms. Fixed now rather than carried into Phase 3, where they'd be buried in unrelated agent work.

### Gaps confirmed + fix design

1. **N+1 in `fetch_similar_capas`** — per-candidate `fetch_actions`/`fetch_rca`/`fetch_capa_type` calls (~3N extra queries for N candidates).
2. **N+1 in `fetch_effective_actions`** — same shape, per-action `fetch_capa`/`fetch_rca`/`fetch_capa_type` (~3×20 extra queries, worse since `fetch_effective_actions` has no result cap going in).
   - **Fix (1+2):** add bulk repository methods — `fetch_actions_bulk(tenant_id, capa_ids)` / `fetch_rca_bulk(tenant_id, capa_ids)` (one `IN (...)` query each, returning `dict[capa_id, ...]`), plus an in-process master-data cache (`severity`/`priority`/`capa_type`/`category` — ~30 rows total, effectively static for a process lifetime) so those lookups stop round-tripping per row. Reduces both functions from O(N) extra queries to O(1) (3 fixed queries regardless of N).
3. **No ranking after merging sql+vector results** — concatenation order, not relevance order.
4. **Weak SQL fallback compounds with #3** — when sql has no site/category to filter on, it returns "most recent CAPAs" (often irrelevant), and because there's no ranking, that irrelevant batch sits at the *front* of `similar_capas`, ahead of genuinely-relevant vector hits.
   - **Fix (3+4, one mechanism):** give every `SimilarCapaSummary` a real `similarity_score` at merge time — sql's structural match (real site/category hit) scores `1.0`; sql in fallback mode scores `0.1` (kept as a last-resort signal, not discarded, but ranked low); vector hits keep their cosine score. Sort the merged list by score desc, truncate to a capped top-N before returning. Fallback junk sinks instead of leading; vector's semantic relevance actually drives ordering when it's the better signal.
5. **NL2SQL always asks the same hardcoded question** ("list employees and roles at site X") regardless of CAPA content.
   - **Fix:** build the question from `root_cause_category` → role-keyword mapping (Training Gap → training/HR roles, Equipment Fault → maintenance/engineering roles, etc.), falling back to a generic "roles relevant to category X at site Y" question when no mapping hits. Still exactly one NL2SQL call per request — no cost increase, smarter question.
6. **No similarity threshold on vector search** — `vector_retrieval.py`'s 3 search functions return top-k unconditionally, including low-confidence/irrelevant hits when nothing in the collection is actually close.
   - **Fix:** `config.VECTOR_SIMILARITY_THRESHOLD` (default `0.2` — a starting point, not empirically tuned; real tuning is Phase 6's job per the original plan), filter all 3 search functions to drop results below it.

### Files touched
`repositories/base.py` + `postgres.py` (bulk fetch methods, master cache), `retrieval/sql_retrieval.py` (use bulk methods, score fallback vs. structural matches), `retrieval/context_retrieval.py` (merge-then-rank-then-truncate), `retrieval/nl2sql.py` (dynamic question builder), `retrieval/vector_retrieval.py` (threshold filter), `config.py` (`VECTOR_SIMILARITY_THRESHOLD`).

### Checkpoint 2b
- Query count for `fetch_similar_capas`/`fetch_effective_actions` measured before/after — confirmed O(1) instead of O(N).
- `similar_capas` ordering test: construct a case where sql is in fallback mode and vector has a strong real hit — assert the vector hit ranks above the fallback CAPAs.
- NL2SQL question varies by `root_cause_category` — assert at least 2 different categories produce different questions.
- Vector threshold: inject a deliberately irrelevant query, confirm low-similarity results are filtered out (collection-dependent — assert on count/score, not exact IDs).
- Full existing Phase 2 test suite (26 tests: 16 guard + 10 ContextPackage) re-run, must still pass — this is a hardening pass, not a behavior change to the contract.

### Implementation

**`repositories/base.py` + `postgres.py`** — added `fetch_actions_bulk`/`fetch_rca_bulk`/`fetch_capas_bulk` (one `WHERE capa_id = ANY(%s)` query each, returning `dict[capa_id, ...]`). Added a process-local `_master_cache` dict (keyed `(table, id)`) wrapping `fetch_severity`/`fetch_priority`/`fetch_status`/`fetch_capa_type`/`fetch_category` — each now hits the DB once per distinct id per process, never invalidated (masters are ~30 rows total, effectively static; documented staleness tradeoff in `phases/production.md`).

**`retrieval/sql_retrieval.py`** — `fetch_similar_capas`/`fetch_effective_actions` rewritten to call the bulk methods once instead of looping per-candidate. Also now sets `similarity_score` on every `SimilarCapaSummary`: `1.0` for a real structural (site/category) match, `0.1` for the fallback path (no site/category — "recent CAPAs").

**`retrieval/context_retrieval.py`** — `similar_capas` merge rewritten from "sql list + append non-dup vector" to a proper `dict[capa_id, SimilarCapaSummary]` merge (on a collision, keep whichever side scored higher), then `sorted(..., key=similarity_score, reverse=True)[:config.MAX_SIMILAR_CAPAS]`. NL2SQL question now built per-request via `nl2sql.build_employee_question(site_id, category_id)` instead of a fixed string.

**`retrieval/nl2sql.py`** — added `build_employee_question()` + `_CATEGORY_ROLE_KEYWORDS` (covers all 8 minted categories — `CAT_TRAINING_GAP`, `CAT_EQUIPMENT_FAULT`, `CAT_PROCESS_FAILURE`, `CAT_MISSING_INSPECTION`, `CAT_MANAGEMENT_SYSTEM_WEAKNESS`, `CAT_ENGINEERING_CONTROL_GAP`, `CAT_HUMAN_ERROR`, `CAT_ENVIRONMENTAL_FACTOR`). Unknown/missing category falls back to the original generic question.

**`retrieval/vector_retrieval.py`** — all 3 search functions now drop any result with `(1 - distance) < config.VECTOR_SIMILARITY_THRESHOLD` before returning.

**`config.py`** — `MAX_SIMILAR_CAPAS = 10`, `VECTOR_SIMILARITY_THRESHOLD = 0.2` (starting point, not empirically tuned — real tuning is Phase 6's job per the original plan).

**Live finding during testing:** a richer NL2SQL question (role-targeted instead of the generic one) led the LLM to attempt `capa_rca.contributing_factors ILIKE e.role_title` — a `TEXT[] ILIKE` type error that Postgres rejects at execution time. The guard correctly let it through (syntactically valid single SELECT, whitelisted tables, tenant filter present — nothing about it is actually unsafe, just wrong), and `run_nl2sql`'s existing execution-failure handling degraded it to an empty `NL2SQLResult` rather than crashing — confirms the "guard rejects unsafe SQL, execution-failure handling absorbs merely-wrong SQL" two-layer design works as intended. No retry-on-execution-failure exists (only on guard-rejection/schema-validation at the LLM-output level) — accepted as-is; an execution-failure retry would double NL2SQL latency/cost for a get-it-right-eventually gain that doesn't block the checkpoint.

### How to Test (Checkpoint 2b — passed)

```bash
pytest tests/unit/test_sql_retrieval_bulk.py -v      # 3 tests — bulk methods called once, not per-row
pytest tests/unit/test_nl2sql_questions.py -v         # 3 tests — question varies by category
pytest tests/unit/test_vector_threshold.py -v         # 4 tests — low-similarity results dropped
pytest tests/integration/test_context_retrieval.py -v # 11 tests (10 original + 1 new ranking checkpoint)
pytest tests/ -v                                      # full suite: 50/50 pass
```

1. `test_sql_retrieval_bulk.py`: a fake repository counts calls — `fetch_actions_bulk`/`fetch_rca_bulk`/`fetch_capas_bulk` called exactly once each regardless of 15 or 25 candidates; `fetch_actions`/`fetch_rca`/`fetch_capa` (the old per-row methods) called zero times. Confirms O(1) instead of O(N).
2. Live: `fetch_similar_capas(site_id="SITE_05", category_id="CAT_TRAINING_GAP")` → same 6-CAPA Cluster-A-adjacent set as before, all scored `1.0` (structural match); calling with no site/category → 10 CAPAs all scored `0.1` (fallback).
3. `test_fallback_ranked_below_real_vector_hits` (new, live): a CAPA with no `site_id`/`root_cause_category` (forces sql fallback) but a wire-rope/crane description (real vector signal) → `similar_capas_is_fallback=True`, but every vector-scored entry (0.78–0.82) appears before every fallback-scored entry (0.1) in the final list — confirms #3+#4 fixed together.
4. `test_nl2sql_questions.py`: `CAT_TRAINING_GAP` → training-role question, `CAT_EQUIPMENT_FAULT` → maintenance/engineering-role question, `CAT_MANAGEMENT_SYSTEM_WEAKNESS` → a third distinct question; unknown category / no category → the original generic question (no silent failure).
5. `test_vector_threshold.py`: fake Chroma collection with controlled distances — a distance of `1.5` (score `-0.5`) and `0.95` (score `0.05`) are dropped against the `0.2` default threshold; a distance of `0.1` (score `0.9`) is kept. All 3 search functions (`historical_capas`/`sops`/`regulatory`) tested independently.
6. Full regression: all 39 original Phase 2 tests (13 repository + 16 guard + 10 ContextPackage) still pass unchanged — this was a hardening pass, not a contract change.
