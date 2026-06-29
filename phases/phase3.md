# Phase 3 — Generator Agent

**Status: PHASE 3 COMPLETE.** Checkpoint passed: 55/55 unit tests, 9/10 live integration cases (the 1 miss was a Groq+OpenRouter 429 cascade onto a cold-started local Ollama timeout — an infra/quota artifact, not an agent logic error, same documented pattern as the reference build's own Phase 3 checkpoint).

Goal: given a `CAPARecord` + one `requested_action_type`, produce 1–3 schema-valid `GeneratedAction`s. Single LLM call (`PRIMARY_MODEL`). Validate, retry once on failure, raise structured error on second failure. Mirrors `reference/backend/agents/generator.py`'s actual end-state (not `reference/overview.md`'s older flat spec — verified the real code is the richer requirements/options shape and built against that, per CLAUDE.md's "check actual code, not the doc" rule).

---

## Decisions made this session

### 1. Output shape — requirements/options, not flat description

`reference/overview.md` 3.10.1 describes a flat per-action schema (`description`, single `required_evidence` list). The actual `reference/backend/agents/generator.py` + `generator.jinja2` evolved past that to a richer shape: each action decomposes into `requirements`, each requirement either `mandatory` (exactly 1 option) or optional (2–5 meaningfully different options). This is what real prompt-engineering iteration converged on (lets the user pick from genuine alternatives instead of one rigid sentence). Built against the real code.

### 2. `action_taxonomy` — new table, not a repurposing of `CAPA_CATEGORIES`

Checked: `CAPA_CATEGORIES`/`CAPA_SUBCATEGORIES` (already in our mirror, already populated) are **root-cause** categories (Equipment Fault, Training Gap, etc — 8 values, mapped from `reference/backend/seeds/seed_taxonomy.sql`'s `root_cause_taxonomy`). `action_taxonomy` is a **different**, unrelated table in the reference — 22 rows of `action_type × theme` combinations (e.g. `Corrective` × `Engineering Control`) used only to give the Generator a menu of realistic action shapes to choose from. Not the same concept, not seeded anywhere in our mirror.

Decision: add it as a new **Tier 4 AI-side table** (`CAPA_AI_ACTION_TAXONOMY`), same precedent as `CAPA_RCA` — i.e. an isolated extension that doesn't exist in the real Oracle schema, deletable as one file later. Global (no `TENANT_ID`) since it's pure controlled vocabulary, not tenant data — ported the same 22 rows verbatim from `seed_taxonomy.sql`, VARCHAR string IDs (`AT_001`...) per our ID convention. DDL + static `INSERT ... ON CONFLICT DO NOTHING` live together in `seeds/schema.sql` (no tenant build pipeline involvement, unlike `MSTR_TENANT_EMP`).

### 3. API endpoints now ship per-phase, not deferred to the Orchestrator phase

Revised from Phase 1/2's pattern (agent-module + tests only, no route). From Phase 3 onward, each agent/pipeline phase also gets a minimal route exposing it, so the API surface grows incrementally instead of arriving all at once at the end. The dedicated Orchestrator/API phase later still does the real work: wiring intent-routing, the eval cache, consistent envelopes — these per-phase routes are minimal pass-throughs, expected to be reshaped (not necessarily kept verbatim) once that phase happens.

This phase adds:
- `POST /capa/generate` — Generator (this phase's main deliverable)
- `POST /capa/context` — retrofit for Phase 2 (Context Retrieval), added now since the pattern starts here

### 4. `model_version` — ported `prompt_version()` hash helper

Reference's `AIResponse.model_version` is `"<model>@<8-char hash of prompt file(s)>"` so a prompt edit is distinguishable from a model-name change in audit history. Ported `config.prompt_version()` verbatim; added `config.GENERATOR_MODEL_VERSION`.

---

## Build plan

### Schemas (`models/schemas.py`)
- `ActionOption` (`text: str`)
- `ActionRequirement` (`label`, `mandatory: bool`, `options: list[ActionOption]`) — validated: `mandatory=True` → exactly 1 option, `mandatory=False` → 2–5 options
- `GeneratedAction` (`type`, `title`, `requirements: list[ActionRequirement]` (≥1), `recommended_owner_role`, `recommended_due_date: date`, `required_evidence: list[str]` (≥2), `effectiveness_check_method`, `rationale`, `linked_root_cause`, `confidence_level: ConfidenceLevel`, `similar_capa_reference: Optional[str]`)
- `ActionTaxonomyEntry` (`action_taxonomy_id`, `action_type`, `theme`, `description`)
- `GenerateActionsResponse` (API envelope: `request_id`, `capa_id`, `action_type`, `actions: list[GeneratedAction]`, `model_version`)

### DB (`seeds/schema.sql`)
- `CAPA_AI_ACTION_TAXONOMY` table + 22-row seed insert (Tier 4 section, alongside `CAPA_RCA`)

### Repository (`repositories/base.py` + `postgres.py`)
- `fetch_action_taxonomy(action_type: str) -> list[ActionTaxonomyEntry]` — process-local cache (static reference data, same precedent as the master-data cache)

### Config (`config.py`)
- `prompt_version(*filenames) -> str` (ported from reference)
- `GENERATOR_MODEL_VERSION = f"{PRIMARY_MODEL}@{prompt_version('generator.jinja2')}"`

### Prompt (`prompts/generator.jinja2`)
Ported from reference, adapted to our `ContextPackage` field names (`site_id`/`owner_group_id` not name strings; `enterprise_context: list[NL2SQLResult]` not a `{"results": [...]}` dict; `action_themes` sourced from `fetch_action_taxonomy` via the repository, not raw SQL in the agent).

### Agent (`agents/generator.py`)
`run(agent_input: AgentInput, repo: CapaRepository, num_actions: int = 2) -> list[GeneratedAction]`. Renders prompt → `call_llm(PRIMARY_MODEL)` → parse JSON array → validate each item against `GeneratedAction` → validate due-date windows in code (`Containment` 0–7d, `Corrective` 30–90d, `Preventive` 60–180d, `Risk Mitigation` 14–60d) → retry once with a tailored correction prompt on `JSONDecodeError`/`ValidationError`/due-date violation/truncation → raise on second failure.

### API (`api/routes.py`)
- `POST /capa/generate` — body `CAPARecord` (with `requested_action_type` + optional `num_actions`) → `get_context_package(..., "generator", repo)` → `generator.run(...)` → `write_audit(...)` → `GenerateActionsResponse`
- `POST /capa/context` — body `CAPARecord` + `agent_name` query/body param → `get_context_package(...)` → returns the raw `ContextPackage` (debug/integration use, no audit write — it's not a terminal AI decision)

### Tests
- `tests/unit/test_generator.py` — no network: due-date window validator (4 action types × in/out of window), `ActionRequirement` validators (mandatory/option-count edge cases), JSON-array parsing + type-overwrite-on-mismatch, correction-message selection per exception type. Mirrors `test_nl2sql_guard.py`'s mocked style.
- `tests/integration/test_generator.py` — live Groq + live DB context retrieval, 10 varied `CAPARecord`+`requested_action_type` cases (one per action type at minimum, plus missing-context cases) asserting: correct `type` on every action, `requirements` non-empty with valid mandatory/option shape, `required_evidence` ≥ 2, due date inside the type's window, `confidence_level` valid, `linked_root_cause` non-empty.

---

## Checkpoint 3 — PASSED

- [x] `CAPA_AI_ACTION_TAXONOMY` applied to live `capa_assist` + 22 rows present (verified via `psql -f seeds/schema.sql`, idempotent — `INSERT ... ON CONFLICT DO NOTHING`)
- [x] Unit suite green — 55/55 (`test_generator.py` 26, `test_generate_route.py` 3, plus the 26 pre-existing Phase 2 unit tests unaffected)
- [x] Integration suite — 9/10 live cases (Groq + live DB + live ChromaDB). The 1 failure (`preventive` case) was all 4 Groq keys + all 4 OpenRouter keys returning 429, falling to a cold-started local Ollama that then exceeded the 120s timeout — confirms the 3-tier fallback chain itself works correctly, just ran out of real budget during this test run.
- [x] `POST /capa/generate` route plumbing verified (mocked generator/context/repo — no live quota burned): returns the right action count, writes one audit entry tagged `agent="generator"`, 422 on missing `requested_action_type`, 502 on generator failure.
- [x] `POST /capa/context` added (Phase 2 retrofit) — thin pass-through to `get_context_package`, not separately unit-tested (it's a 3-line wrapper around already-tested `context_retrieval.py`).
- [x] `grep -rln "SELECT \|INSERT INTO\|UPDATE \|DELETE FROM" --include="*.py" .` → unchanged from Phase 2's exemption set (`repositories/postgres.py`, `seeds/load_seed.py`, `retrieval/nl2sql.py`) — `agents/generator.py` calls `repo.fetch_action_taxonomy()`, no raw SQL.

---

## Implementation

**`seeds/schema.sql`** — `CAPA_AI_ACTION_TAXONOMY` (Tier 4, alongside `CAPA_RCA`) + 22-row static seed (`AT_001`-`AT_022`, ported verbatim from `reference/backend/seeds/seed_taxonomy.sql`'s `action_taxonomy` table). Applied clean to live `capa_assist` (`CREATE TABLE` + idempotent insert in the same file — no tenant build pipeline involvement, since this is global controlled vocabulary, not tenant data).

**`models/schemas.py`** — `ActionOption`, `ActionRequirement` (model-validator enforcing exactly-1-option-if-mandatory / 2-5-options-if-optional), `GeneratedAction` (field-validators: ≥1 requirement, ≥2 `required_evidence` items), `ActionTaxonomyEntry`, `GenerateActionsResponse` (API envelope).

**`repositories/base.py` + `postgres.py`** — `fetch_action_taxonomy(action_type)`, process-local cache keyed by `action_type` (22 rows total, static for a process lifetime — same precedent as the Phase 2 master-data cache).

**`config.py`** — ported `prompt_version()` (sha256 hash of prompt file contents, truncated to 8 chars) from `reference/backend/config.py`; `GENERATOR_MODEL_VERSION = f"{PRIMARY_MODEL}@{prompt_version('generator.jinja2')}"`.

**`prompts/generator.jinja2`** — ported from reference near-verbatim, adapted to this rebuild's `ContextPackage` shape: `site_id`/`owner_group_id` (string IDs, not resolved name strings — the reference had `Site`/`Department` name strings available from its old schema, ours doesn't carry those through `ContextPackage` and resolving them wasn't worth a new round-trip for a Phase 3 prompt block); `enterprise_context` rendered as `list[NL2SQLResult]` (`result.rows`) instead of the reference's flat `{"results": [...]}` dict shape.

**`agents/generator.py`** — `run(agent_input, repo, num_actions=2)`. Mirrors reference's actual end-state logic: renders the prompt (fetching `action_themes` via `repo.fetch_action_taxonomy()`, not raw SQL — the one change from the reference's direct `execute_query()` call, made to respect this rebuild's repository-layer rule), single `call_llm(PRIMARY_MODEL)` call, parses the JSON array, force-overwrites any type mismatch the model returns, validates due-date windows in code (not just prompted), retries once with a failure-specific correction message, raises `ValueError` on a second failure. `recommended_due_date` is typed `date` in `GeneratedAction` (not `str` like the reference) since Pydantic parses the ISO string for free and `_validate_due_date_windows` no longer needs its own `date.fromisoformat` try/except.

**`api/routes.py`** — `POST /capa/generate`: validates `requested_action_type` present (422 if not) → `get_context_package(..., "generator", repo)` → `generator.run(...)` → on `ValueError` (both retries failed) returns 502 → on success builds `GenerateActionsResponse`, writes one `capa_ai_audit_trail` row tagged `agent="generator"`, returns it. `POST /capa/context` (Phase 2 retrofit, per decision 3): thin wrapper exposing `get_context_package` directly, body `CAPARecord` + `agent_name` query param (defaults `"generator"`) — no audit write, since retrieving context isn't itself a terminal AI decision (the agent that consumes it writes the audit row).

**Live finding during testing:** under real Groq quota pressure (free-tier keys, shared across this whole rebuild's testing), one of 10 live cases (`preventive`) cascaded through all 4 Groq keys (429) → all 4 OpenRouter keys (429) → cold-started local Ollama → exceeded the 120s fallback timeout. Confirms `services/llm.py`'s 3-tier fallback chain itself is working as designed (it didn't silently fail or skip a tier) — the failure is a real-world quota ceiling, not a code defect. Not fixed/retried further since it's an external rate limit, not a Phase 3 scope item.

### How to Run

```bash
conda activate capa-ai
cd service
psql -h localhost -p 5433 -U postgres -d capa_assist -f seeds/schema.sql   # adds CAPA_AI_ACTION_TAXONOMY (idempotent)
uvicorn main:app --reload --port 8001
```

### How to Test (Checkpoint 3 — passed)

```bash
pytest tests/unit/test_generator.py -v          # 26 tests — validators, due-date windows, parsing, retry logic (mocked, no network)
pytest tests/unit/test_generate_route.py -v     # 3 tests — route plumbing (mocked, no network/DB)
pytest tests/integration/test_generator.py -v   # 10 tests — live Groq + live DB + live ChromaDB
pytest tests/ -v                                # full suite
```

---

## Sub-Phase 3b — Prompt redesign (skeleton/enrich split)

A user code-review pass on `generator.jinja2`/`agents/generator.py` raised 7 points before Phase 4 work continued. Addressed here rather than carried forward, same rationale as 2b.

### Decisions

**1. Split into 2 LLM calls — skeleton then enrich.** The single-call prompt was asking one small model (`gpt-oss-20b`) to do everything at once: read 5 context sources, pick a theme, decompose into requirements, write evidence/due-date/rationale, and stay JSON-valid throughout. Split into:
- **Skeleton call** (`prompts/generator/skeleton.jinja2`) — decides *what* the action is: `type`, `title`, `requirements` (the mandatory/optional decomposition), `linked_root_cause`, `rationale`. Only needs the CAPA's own fields + action-type themes + existing-actions context. No historical/SOP/regulatory/enterprise context — keeps this call's prompt small and focused on one cognitive task.
- **Enrich call** (`prompts/generator/enrich.jinja2`) — takes the skeleton(s) verbatim and adds the parts that genuinely need the heavy context: `recommended_owner_role`, `recommended_due_date`, `required_evidence`, `effectiveness_check_method`, `confidence_level`, `similar_capa_reference`. This is where similar_capas/effective_actions/SOPs/regulatory/enterprise_context get used.

Tradeoff accepted: 2x LLM calls per `/capa/generate` request (latency + cost), and a new failure mode (enrich's output array must positionally match the skeleton array length, or it's treated as a validation failure and retried). Worth it for: each call is now a single cognitive task, smaller prompts per call (less truncation risk than the old combined call), and either call can be retried/corrected independently without re-deciding the other half.

**2. Rationale constrained to 1-2 sentences.** Added an explicit instruction + a soft length check (`ActionSkeleton` field validator, ~400 char ceiling) so the model doesn't write an essay.

**3. Prompt modularity via Jinja2 includes.** Both `skeleton.jinja2` and `enrich.jinja2` are now thin top-level files that `{% include %}` shared fragments: `_capa_context.jinja2` (CAPA fields), `_existing_actions.jinja2` (sibling actions on this CAPA), `_action_type_guidance.jinja2` (type definition + themes, skeleton only), `_historical_context.jinja2` (similar_capas/effective_actions/SOPs/regulatory/enterprise, enrich only). No behavior change — same render, same token cost — just maintainable source instead of one 186-line file.

**4. `_DUE_DATE_WINDOWS` moved to `config.py`** as `DUE_DATE_WINDOWS` — it's business logic (regulatory/operational expectation per action type), not agent-internal trivia. `enrich.jinja2` now renders the windows from this dict instead of repeating hardcoded day-ranges in the prompt text, so the prompt and the code-level validator can never drift apart.

**5. New `CAPARecord.existing_actions: list[ExistingActionRef]` field — not a repurposing of `actions`.** Checked first: `CAPARecord.actions` is already used by the Evaluator (`api/routes.py` `/capa/evaluate`, built in Phase 4) as `actions[0]` = the *single* ad-hoc action text being scored — a different meaning entirely from Generator's "list of sibling actions already on this CAPA, for dedup/build-on context." Repurposing `actions` would have silently broken the Evaluator's read of it. Added a distinct field instead: `ExistingActionRef(type: ActionType, description: str)` — now `_existing_actions.jinja2` can say "A1 is `Corrective` and covers X — build on it, don't repeat" instead of the old plain-string "don't duplicate this sentence," and the skeleton call gets real signal to differentiate new work from what already exists.

**6/7. Org-name hardcoding + prompt reproducibility — see `phases/production.md`.** `config.ORG_NAME` (env-overridable, defaults `"AcerTech Industries"`) replaces the hardcoded org name in both new templates. Audit-trail prompt-reproducibility (point 7) is documented as a known gap in `production.md`, not fixed this pass — storing full rendered prompts in `capa_ai_audit_trail` would duplicate `capa_ai_context_packages` data and bloat audit rows; current `model_version` hash + git history is judged sufficient pre-production.

### Build plan

- `config.py` — `DUE_DATE_WINDOWS` (moved from `agents/generator.py`), `ORG_NAME`, `GENERATOR_MODEL_VERSION` rehashed over both new prompt files.
- `models/schemas.py` — `ExistingActionRef`, `ActionSkeleton` (rationale length-validated), `ActionEnrichment`; `CAPARecord.existing_actions` added (distinct from `actions`).
- `prompts/generator/` — `_capa_context.jinja2`, `_existing_actions.jinja2`, `_action_type_guidance.jinja2`, `_historical_context.jinja2`, `skeleton.jinja2`, `enrich.jinja2`. Old flat `prompts/generator.jinja2` deleted (fully superseded).
- `agents/generator.py` — rewritten `run()`: render+call+parse+validate skeleton (retry once) → render+call+parse+validate enrich against the skeleton (retry once, including a length-mismatch correction) → merge skeleton+enrichment per index into `GeneratedAction` → validate due-date windows from `config.DUE_DATE_WINDOWS`.
- Tests rewritten for the 2-call flow (unit: mocked, asserts both calls happen in order with correct content; integration: same 10 live cases, now 2 real LLM calls each).

### Checkpoint 3b — PASSED

- [x] Unit suite green for the new skeleton/enrich split — 29 generator tests (validators, merge logic, retry-on-length-mismatch, 2-call ordering) + 182/182 full unit suite (no regressions in the separately-built Evaluator/Scoring suite)
- [x] Integration suite green — 10/10 live cases, 2 real LLM calls each (Groq), ~150s total
- [x] `existing_actions` demonstrably changes skeleton output — `with_existing_actions` case asserts the generated title never exactly repeats an existing action's description; passed live
- [x] `ORG_NAME` is not hardcoded anywhere in the new templates — `grep -ril "acertech" prompts/generator/` returns nothing
- [x] `production.md` updated with the org-name-genericization note (generator only — other agents' prompts not yet audited) and the audit-trail reproducibility gap

### Implementation

**`config.py`** — `DUE_DATE_WINDOWS` (moved from `agents/generator.py`'s `_DUE_DATE_WINDOWS`), `ORG_NAME` (env-overridable, default `"AcerTech Industries"`), `GENERATOR_MODEL_VERSION` rehashed over `generator/skeleton.jinja2` + `generator/enrich.jinja2`.

**`models/schemas.py`** — `ExistingActionRef` (`type`, `description`) added alongside `ActionType`'s definition (not repurposing `CAPARecord.actions`, which the Evaluator already owns for a different meaning — see decision 5); `CAPARecord.existing_actions: Optional[list[ExistingActionRef]]` added as a new field. `ActionSkeleton` (requirements ≥1, rationale ≤400 chars) and `ActionEnrichment` (required_evidence ≥2) replace the old single-step `GeneratedAction` fields, split along the skeleton/enrich boundary; `GeneratedAction` itself is unchanged in shape — it's now populated by merging one `ActionSkeleton.model_dump()` + one `ActionEnrichment.model_dump()` by index instead of coming straight from one LLM response.

**`prompts/generator/`** — old flat `generator.jinja2` deleted, replaced by `skeleton.jinja2` + `enrich.jinja2` (top-level, one per call) each `{% include %}`-ing shared fragments: `_capa_context.jinja2`, `_existing_actions.jinja2` (skeleton only — now renders `[type] description` per existing action with "build on it, don't repeat" framing), `_action_type_guidance.jinja2` (skeleton only), `_historical_context.jinja2` (enrich only). `enrich.jinja2` renders `config.DUE_DATE_WINDOWS` directly into the prompt text instead of repeating hardcoded day-ranges.

**`agents/generator.py`** — rewritten around a shared `_call_with_retry()` helper (render once, retry once with a failure-specific correction turn, raise on a second failure) used by both calls. `run()`: skeleton call (`_render_skeleton_prompt` → `_parse_skeletons` → validates `ActionSkeleton[]`) → enrich call (`_render_enrich_prompt`, which serializes the skeletons to JSON and embeds them in the prompt → `_parse_enrichments`, which raises if the returned array length doesn't match the skeleton count — this is the new failure mode the design accepted) → merge by index into `GeneratedAction` → `_validate_due_date_windows` (now reading `config.DUE_DATE_WINDOWS`).

**`tests/unit/test_generator.py`** — rewritten for the 2-call flow: `ActionSkeleton`/`ActionEnrichment` validators, due-date windows (now via `config.DUE_DATE_WINDOWS`), `_parse_skeletons`/`_parse_enrichments` (including the length-mismatch case), and 5 `run()` tests asserting both calls happen in order, `existing_actions` renders into the skeleton prompt specifically (not the enrich prompt), and each call's retry-then-raise behaves independently.

**`tests/integration/test_generator.py`** — `with_existing_actions` case switched from the old `actions=["..."]` (which would have collided with the Evaluator's reading of that field) to `existing_actions=[ExistingActionRef(...)]`; added an assertion that the generated title never exactly matches an existing action's description.

### How to Test (Checkpoint 3b — passed)

```bash
pytest tests/unit/test_generator.py -v          # 29 tests — validators, 2-call ordering, retry/length-mismatch logic
pytest tests/unit -q                            # full unit suite — 182 passed
pytest tests/integration/test_generator.py -v   # 10 tests — live Groq (2 calls/case) + live DB + live ChromaDB
```
