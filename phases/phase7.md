# Phase 7 — Orchestrator + API Layer

Goal: the last individual-agent phase (Phase 6, Explainability) is done.
Per `CLAUDE.md`'s build approach, remaining work is "Orchestrator/API layer"
— but unlike `reference/plan.md`'s Phase 5 (one big-bang wiring phase), this
build already shipped a route alongside every agent phase (3-6). So there's
no greenfield wiring left to do. What's actually missing, scoped with the
user up front:

1. **Orchestrator extraction.** `api/routes.py` has grown into 4 near-
   identical "resolve context → call agent → score → persist → audit" blocks
   with no separation between HTTP concerns and pipeline sequencing. The
   `orchestrator/` package has existed since Phase 0 scaffolding
   (`orchestrator/__init__.py`, empty) but nothing was ever put in it —
   every phase's route grew the orchestration logic straight into the route
   handler instead. Phase 7 finally fills that package.
2. **Read endpoints.** Nothing in this build can read back a `Capa`, list
   CAPAs, or inspect the audit trail — every phase so far only adds AI
   write/compute endpoints. There's no UI in this rebuild (API service only,
   per `CLAUDE.md`), but without *some* way to inspect what's in the mirror
   and what the AI did, there's no way to verify behavior except `psql`.

Explicitly out of scope (confirmed with user): auth, rate limiting, CORS,
and the rest of `phases/production.md`'s hardening backlog — those need real
infra/deployment decisions this rebuild isn't making yet, and `production.md`
already tracks them as deferred hard-blockers, not silent gaps.

---

## Decisions made this session

### 1. Orchestrator = pipeline sequencing, not routing-only

The reference's locked rule was "Orchestrator = pure routing, no business
logic; Context Retrieval Agent does the selective-retrieval routing." That
worked there because Phase 5 was the *only* place wiring existed. Here, the
"business logic" of stringing 4 agent calls together (context retrieval →
agent → scoring → cache → persistence → audit) has lived in `api/routes.py`
since Phase 3 and grown by accretion. Phase 7 moves that sequencing into
`orchestrator/dispatch.py` as one `async def run_<verb>(capa, repo) -> *Response`
function per endpoint. `api/routes.py` becomes genuinely routing-only: parse
the request, call `get_repository()`, call the matching `dispatch.run_*`,
return what it returns. This is a closer match to the *intent* behind
"Orchestrator/API layer" than a literal copy of the reference's narrower
definition would be — flagged here rather than silently reinterpreted.

`HTTPException` (404/422/502) still gets raised from inside
`dispatch.py` rather than translated through a custom exception type at the
boundary. FastAPI's `HTTPException` is a plain exception class, not
framework-coupled business logic — inventing a parallel `OrchestratorError`
hierarchy just to re-raise as `HTTPException` one layer up would be
ceremony with no behavioral difference. Noted as a conscious shortcut, not
an oversight.

### 2. Shared helpers move with their callers

`_resolve_action_text` (used by evaluate/improve/explain) and
`_resolve_evaluation` (used by improve/explain) move into `dispatch.py`
unchanged — they're pipeline-sequencing helpers, not HTTP-shaping helpers,
so they belong with the functions that use them, not in `routes.py`.

### 3. Existing route tests retarget their monkeypatches, not rewritten

`tests/unit/test_{generate,evaluate,improve,explain}_route.py` currently
monkeypatch `routes_mod.evaluator`/`routes_mod.generator`/etc. and
`routes_mod.get_context_package` directly, since those names lived in
`api/routes.py`'s module namespace. After extraction those names live in
`orchestrator.dispatch`'s namespace instead — the tests' patch targets move
accordingly (`dispatch_mod.evaluator.run`, `dispatch_mod.get_context_package`,
...). `routes_mod.get_repository` stays patched on `routes_mod` since
`api/routes.py` still owns obtaining the repository (it's an HTTP-request-
scoped concern: one repo per request, passed down). Test *behavior*
(payloads, assertions, status codes) is unchanged — this is a pure
patch-target relocation, confirming the refactor didn't change what the
routes actually do.

### 4. Read endpoints: tenant_id is a required query param, no defaulting

No auth exists yet (explicitly deferred, `production.md`), so there's no
session to infer a tenant from. Every write endpoint already requires
`tenant_id` in the request body (`CAPARecord.tenant_id`); the new read
endpoints require it as a query param for the same reason — never default to
`config.CAPA_TENANT_ID` silently, since that's a seed-time convenience
constant, not a runtime auth boundary substitute.

### 5. Three read endpoints, minimal new repository surface

- `GET /capa/{capa_id}` — one CAPA + its actions + its RCA record, the
  "detail view" shape. New `CapaDetailResponse` schema (composition of
  existing `Capa`/`CapaAction`/`CapaRCA` — no new domain schema needed).
  404 if the CAPA doesn't exist for that tenant.
- `GET /capas` — paginated list, optional `site_id`/`status_id` filters.
  New `repo.fetch_capas()` + `repo.count_capas()` (separate count query,
  not `COUNT(*) OVER()` window — simpler, and this table is seed-scale so
  the extra round trip is irrelevant). New `CapaListResponse{items, total,
  limit, offset}` envelope.
- `GET /capa/{capa_id}/audit` — paginated audit trail rows for one CAPA.
  `capa_ai_audit_trail` has no `capa_id` column (by design — it's keyed by
  `request_id`, with `input_payload` JSONB holding whatever the caller sent,
  which always includes `capa_id` for every AI endpoint in this build); the
  new `repo.fetch_audit_trail()` filters on `input_payload->>'capa_id'`
  instead of adding a denormalized column for a dev-scale, low-QPS read
  path. Reuses `AuditTrailEntry` in a new `AuditTrailListResponse` envelope.

`config.DEFAULT_LIST_LIMIT = 50` / `config.MAX_LIST_LIMIT = 200` — named
constants (this build's convention, see `MAX_SIMILAR_CAPAS`), not magic
numbers in the route signature. Matches the limit/max the reference's own
`CLAUDE.md` documented for its (never-built-here) `GET /capas`.

### 6. No write endpoints added

`POST /capas` (create) and `GET /sites`/`GET /departments` from the
reference's `CLAUDE.md` were frontend-form support endpoints — this rebuild
has no frontend (`CLAUDE.md`: "API service only, no frontend"), so they have
no caller. Not built. If a frontend or seed-ingestion path ever needs to
create CAPAs through the API rather than `seeds/load_seed.py`, that's a new
decision for whoever builds that caller, not a thing to speculatively add
now.

---

## Build plan

### Orchestrator (`orchestrator/dispatch.py`, new)
Four functions, one per existing AI endpoint, lifted out of
`api/routes.py` verbatim (logic unchanged, only the module they live in
changes): `run_generate`, `run_evaluate`, `run_improve`, `run_explain`.
Plus the two shared helpers (`_resolve_action_text`, `_resolve_evaluation`)
they call.

### Repository (`repositories/base.py` + `repositories/postgres.py`)
- `fetch_capas(tenant_id, limit, offset, site_id=None, status_id=None) -> list[Capa]`
- `count_capas(tenant_id, site_id=None, status_id=None) -> int`
- `fetch_audit_trail(tenant_id, capa_id=None, agent=None, limit=50, offset=0) -> list[AuditTrailEntry]`
- `count_audit_trail(tenant_id, capa_id=None, agent=None) -> int`

### Schemas (`models/schemas.py`)
- `CapaDetailResponse{capa, actions, rca}`
- `CapaListResponse{items, total, limit, offset}`
- `AuditTrailListResponse{items, total, limit, offset}`

### Config (`config.py`)
- `DEFAULT_LIST_LIMIT = 50`
- `MAX_LIST_LIMIT = 200`

### API (`api/routes.py`)
- 4 existing AI routes shrink to: get repo → `await dispatch.run_*(capa, repo)`.
- 3 new GET routes: `/capa/{capa_id}`, `/capas`, `/capa/{capa_id}/audit`.

### Tests
- Retarget monkeypatches in the 4 existing route test files
  (`dispatch_mod` instead of `routes_mod` for agent/`get_context_package`
  patches; `routes_mod.get_repository` unchanged) — same assertions, proving
  the extraction is behavior-preserving.
- `tests/unit/test_read_routes.py` (new) — mocked repo: `/capa/{id}` 200 +
  404, `/capas` pagination + filters, `/capa/{id}/audit` pagination,
  `tenant_id` required (422 if missing — FastAPI's own validation, not
  hand-written).
- `tests/integration/test_read_routes.py` (new) — against the real seeded
  DB (self-skips if down, matching every other integration suite): fetch a
  known seeded `capa_id`, list capas with a real `site_id` filter, fetch the
  audit trail after issuing a live `/capa/evaluate` call in the same test.

---

## How to Run

```bash
conda activate capa-ai
cd service
uvicorn main:app --reload --port 8001
```

## How to Test (Checkpoint 7)

```bash
pytest tests/unit/test_generate_route.py tests/unit/test_evaluate_route.py tests/unit/test_improve_route.py tests/unit/test_explain_route.py -v
pytest tests/unit/test_read_routes.py -v
pytest tests/integration/test_read_routes.py -v
pytest tests/ -v
```

## Checkpoint 7 — PASSED (with one pre-existing environment caveat, see below)

- [x] `orchestrator/dispatch.py` built — `run_generate`/`run_evaluate`/
      `run_improve`/`run_explain` + the two shared helpers, logic moved
      unchanged out of `api/routes.py`.
- [x] `api/routes.py` shrunk to routing-only: each of the 4 AI POST routes is
      now `repo = get_repository(); return await dispatch.run_*(capa, repo)`.
      3 new GET routes added (`/capa/{capa_id}`, `/capas`,
      `/capa/{capa_id}/audit`), all requiring `tenant_id` as a query param.
- [x] `repositories/base.py` + `repositories/postgres.py` —
      `fetch_capas`/`count_capas`/`fetch_audit_trail`/`count_audit_trail`
      added. Audit filtering on `input_payload->>'capa_id'` (no schema
      change — `capa_ai_audit_trail` has no `capa_id` column by design).
- [x] `models/schemas.py` — `CapaDetailResponse`/`CapaListResponse`/
      `AuditTrailListResponse` added (composition only, no new domain
      fields). `config.py` — `DEFAULT_LIST_LIMIT`/`MAX_LIST_LIMIT`.
- [x] The 4 existing route test files retargeted their agent/
      `get_context_package` monkeypatches from `routes_mod` to
      `orchestrator.dispatch` — same payloads/assertions, all still pass,
      confirming the extraction is behavior-preserving.
- [x] `tests/unit/test_read_routes.py` (new, 7 tests) — mocked repo: 200/404
      on `GET /capa/{id}`, 422 when `tenant_id` omitted, pagination envelope
      shape on `GET /capas`, 422 on `limit` over `MAX_LIST_LIMIT`, audit
      list shape on `GET /capa/{id}/audit`.
- [x] `tests/integration/test_read_routes.py` (new, 5 tests) — against the
      real seeded dev DB: fetch `CAPA_0001`, 404 on an unknown id, list
      pagination, `site_id` filter correctness, and an audit-trail
      round-trip after a live `/capa/evaluate` call.
- [x] Full unit suite: 226/226 passing (219 pre-Phase-7 + 7 new), zero
      regressions.
- **Caveat — pre-existing, not caused by this phase:** in this dev
  environment, the conda env's `SSL_CERT_FILE` activation variable points
  at `<env>/ssl/cacert.pem`, which doesn't exist (the env's `ssl/` directory
  is missing entirely — `certifi` is installed and has a valid
  `cacert.pem`, but nothing points `SSL_CERT_FILE` at it). Every test that
  makes a live `httpx` call to Groq/OpenRouter fails with
  `FileNotFoundError` building the SSL context — confirmed by re-running
  `tests/integration/test_explainability.py` and `test_generator.py`
  (pre-existing tests, unrelated to Phase 7) and seeing the identical
  failure. This blocks `test_read_routes.py::test_audit_trail_reflects_a_live_evaluate_call`
  (it calls live `/capa/evaluate`, which calls the live LLM) along with
  every other live-LLM integration test in the suite (30 failed across the
  whole run, all the same root cause, none specific to this phase's code).
  Not fixed here — it's a local environment repair (fix `SSL_CERT_FILE` or
  unset it so Python falls back to `certifi`), not a code change, and out
  of this phase's confirmed scope (auth/infra hardening was explicitly
  deferred). Flagged to the user; fix on request.
