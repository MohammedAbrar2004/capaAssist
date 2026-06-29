# Phase 0 — Setup

**Status:** Complete. Checkpoint passed.

> **Updated by Phase 1:** Phase 1 established that the real SoapBox data lives in **Oracle** (multi-tenant), but decided **not** to touch live Oracle during the build. Instead we build against **PostgreSQL `capa_assist`** (the Phase 0 setup stays) as a faithful mirror of the relevant Oracle subset, behind a **repository/adapter layer** so the backend can be swapped to Oracle later. So the Postgres config from Phase 0 is still in use — now with a `DB_BACKEND` flag, `CAPA_TENANT_ID` scoping, and a `repositories/` package added. Folder structure, FastAPI skeleton, logging, conda env: unchanged. See `phase1.md` for the current DB architecture.

This file is the single source of truth for Phase 0. Right now it holds the plan we agreed on. Once Phase 0 is implemented and tested, this file gets updated in place to also cover: what it does, how it does it, how to run it, how to test it. Nothing about Phase 0 should live only in chat history — if it's decided, it's here.

---

## Goal

Scaffold `service/` — folder structure, environment, dependencies, config skeleton, `.env` — so every later phase has a place to put its code, with concerns already separated correctly. No agent logic, no DB schema, no seed data in this phase.

## Decisions Made

| Decision | Value |
|---|---|
| Conda env | Reuse `capa-ai` (same as reference) — Python 3.11 |
| Core libs | FastAPI, ChromaDB, fastembed, psycopg2, Pydantic v2, httpx, Jinja2, pytest — same as reference |
| Database | `capa_assist` (new db, same Postgres credentials as `reference/.env`, different name) |
| `.env` location | Inside `service/` (not repo root, unlike reference) |
| Orchestrator | Separated from HTTP layer: `orchestrator/router.py` (pure routing, no FastAPI types) vs `api/routes.py` (HTTP only, calls orchestrator). Reference conflated these two. |
| Vector client lifecycle | Separated from query logic: `services/vector_store.py` (Chroma client singleton, thread-safe) vs `retrieval/vector_retrieval.py` (query functions). Reference had this lazy-inited inline and not thread-safe (caused a real bug, see `reference/analysis.md`). |
| NL2SQL | Separated from `sql_retrieval.py` into its own `retrieval/nl2sql.py`. Reference mixed both concerns in one file. |
| Tests | Split `tests/unit/` (mocked, no network, fast) and `tests/integration/` (live DB/LLM). Reference had no such split — flagged in `analysis.md` as a real gap (checkpoint accuracy numbers weren't reproducible). |
| Logging | One `logging_config.py` module, no print()/logger mixing (reference had this inconsistency — flagged in `analysis.md`). |

## Folder Structure

```
service/
├── main.py                    # FastAPI app entrypoint only
├── config.py                  # models, paths, weights, thresholds, DB conf, RETRIEVAL_CONFIG
├── requirements.txt
├── .env                       # git-ignored, credentials for capa_assist + LLM keys
├── models/
│   └── schemas.py             # Pydantic contracts — source of truth
├── services/
│   ├── db.py                  # ThreadedConnectionPool wrapper
│   ├── llm.py                 # call_llm/call_llm_json, 3-tier fallback (Groq -> OpenRouter -> Ollama)
│   └── vector_store.py        # Chroma client singleton (thread-safe)
├── retrieval/
│   ├── normalize.py
│   ├── enrich.py
│   ├── sql_retrieval.py
│   ├── nl2sql.py
│   ├── vector_retrieval.py
│   └── context_retrieval.py   # assembles ContextPackage
├── agents/
│   ├── generator.py
│   ├── evaluator.py
│   ├── improver.py
│   └── explainability.py
├── engines/
│   └── scoring_engine.py      # pure Python, no LLM
├── orchestrator/
│   └── router.py              # pure routing logic
├── api/
│   ├── routes.py               # thin HTTP layer, calls orchestrator
│   └── dependencies.py
├── prompts/
│   └── *.jinja2
├── data/
│   ├── sops/
│   └── regulatory/
├── seeds/                      # reserved, Phase 1 territory
├── logging_config.py
└── tests/
    ├── unit/
    └── integration/
```

## What's Deferred to Later Phases

- **DB schema design** — Phase 1 (Seed Data). Not discussed yet.
- **Vectorization pipeline for live/new CAPAs** — design agreed conceptually, build deferred to Phase 2 (Context Retrieval Agent):
  - 3 Chroma collections seeded once in Phase 1: `historical_capas`, `sop_documents`, `regulatory_documents`.
  - SOPs/regulatory: static, re-vectorized only on manual trigger when org content changes.
  - `historical_capas`: grows over time via a standalone batch script (not event-driven on every write — keeps vectorization off the request path). Script selects CAPA actions where `status='Closed'` AND `effectiveness_result IS NOT NULL` AND `vectorized_at IS NULL`, embeds them, upserts into the collection, then stamps `vectorized_at`. Idempotent by construction — no need to query Chroma for existence checks before upsert.
  - Structured/live data (site, dept, severity, status, etc.) is always retrieved via SQL, never via vector search — vector search is supplemental semantic similarity on root-cause text only.

## Implementation

Everything in the Folder Structure section above was created exactly as planned, with these contents:

- **`config.py`** — loads `service/.env` via `python-dotenv` (`override=True`). Exposes paths (`DATA_DIR`, `SOPS_DIR`, `REGULATORY_DIR`, `CHROMA_PATH`, `PROMPTS_DIR`, `SEEDS_DIR`), DB config (`DB_HOST/PORT/USER/PASSWORD/NAME`, `DATABASE_URL` built with `urllib.parse.quote_plus` on user/password — fixes the unencoded-special-characters bug flagged in `reference/analysis.md`), `NL2SQL_DATABASE_URL` (falls back to `DATABASE_URL` until a dedicated read-only role exists), the LLM fallback chain config (`GROQ_API_KEYS`/`OR_API_KEYS` lists, base URLs, `PRIMARY_MODEL`/`LIGHT_MODEL`/`OR_*`/`OLLAMA_*` model names), `LLM_DEBUG_LOGGING` flag, and the embedding model name. `RETRIEVAL_CONFIG`, `DIMENSION_WEIGHTS`, `WEAKNESS_THRESHOLDS` are intentionally **not** defined yet — they belong to Phase 2 (Context Retrieval) and Phase 4 (Scoring Engine) respectively.
- **`logging_config.py`** — single `get_logger(child=None)` function. Configures one `StreamHandler` on stderr, `propagate=False`, logger name `capa_ai` (or `capa_ai.<child>`). Configuration happens once via a module-level guard, not per-call — safe to call `get_logger()` from any module without double-attaching handlers.
- **`api/routes.py`** — `APIRouter` with one `GET /health` endpoint returning `{"status": "ok"}`. No other routes yet — those land with their respective agent phases.
- **`main.py`** — `FastAPI()` instance, includes `api.routes.router`. No middleware, no startup hooks yet (DB pool / Chroma client lifecycle wiring is Phase 1/2 work).
- All other packages (`models/`, `services/`, `retrieval/`, `agents/`, `engines/`, `orchestrator/`, `tests/unit/`, `tests/integration/`) exist as empty packages (`__init__.py` only) — reserved, no logic yet. `prompts/`, `seeds/`, `data/sops/`, `data/regulatory/` exist as empty dirs (`.gitkeep`).
- **`requirements.txt`** — same dependency set as `reference/backend/requirements.txt` (FastAPI, uvicorn, Pydantic v2, psycopg2-binary, chromadb, fastembed, psutil, httpx, python-dotenv, jinja2, pytest, pytest-asyncio).
- **`.env`** — lives in `service/` (not repo root). Same Postgres credentials as `reference/.env` (`localhost:5433`, user `postgres`), `DB_NAME=capa_assist` (the new db, already created and confirmed reachable), and the same Groq (4 keys) + OpenRouter (4 keys) keys as the reference project. `LLM_PROVIDER=groq`.
- **`.gitignore`** — `.env`, `__pycache__/`, `*.pyc`, `data/chroma/`, `.pytest_cache/`.

Conda env: reused `capa-ai` (already existed from the reference project) — all required packages were already present at compatible/newer versions (e.g. `fastapi==0.136.3`, `pydantic==2.13.4`, `chromadb==1.5.9`), no fresh installs needed.

## How to Run

```bash
conda activate capa-ai
cd service
uvicorn main:app --reload --port 8001
```

Health check: `curl http://localhost:8001/health` → `{"status":"ok"}`. Interactive docs at `http://localhost:8001/docs`.

> Port 8000 hit `WinError 10013` on this machine (Windows-reserved/excluded port range, not an app issue) — standardized on **8001** for this project.

## How to Test

No automated tests yet — Phase 0 has no logic worth unit testing beyond config loading, which was verified manually:

```bash
conda activate capa-ai
cd service
python -c "import config; print(config.DATABASE_URL)"   # confirms .env loads, password/user URL-encoded correctly
```

**Checkpoint 0 (passed):**
1. `python -c "import config"` — loads `.env`, builds `DATABASE_URL`, no errors. 4 Groq keys + 4 OpenRouter keys detected.
2. `uvicorn main:app --port 8001` — boots clean, no warnings.
3. `GET /health` → `200 {"status":"ok"}`.
4. `psycopg2.connect(config.DATABASE_URL)` → connects, `SELECT current_database()` returns `capa_assist` (PostgreSQL 17.10) — confirms the new db is reachable with the credentials in `.env`.

Real automated `tests/unit/` and `tests/integration/` suites start in Phase 1 once there's schema/retrieval logic worth testing.
