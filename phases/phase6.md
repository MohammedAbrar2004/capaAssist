# Phase 6 — Explainability Agent

Goal: given a cached/fresh `EvaluationResult` + `ScoringResult` + action text,
produce a plain-language explanation (no jargon, ≤120 words) of why an action
scored the way it did. This is the last agent in the evaluation chain — per
`reference/overview.md` 3.8, it turns the Evaluator's structured weakness
list into something a non-technical EHS field user can read. Final agent
before Phase 7 wraps the remaining orchestrator/API polish (most of which is
already incrementally built per-phase in this codebase, unlike the
reference's deferred big-bang Phase 5).

Reference build (`reference/backend/agents/explainability.py` +
`prompts/explainability.jinja2`) has a finished version. It is the simplest
agent in the system: no retrieval, one cheap LLM call, prose output, never
raises (returns a deterministic fallback string on LLM failure instead of a
502). That non-blocking behavior is the one thing this agent does
differently from every other agent in this build — carried over verbatim.

---

## Decisions made this session

### 1. No context retrieval — confirmed already wired

`config.RETRIEVAL_CONFIG["explainability"] = []` already exists (set up in
Phase 2 alongside the other agents' configs, unused until now). The
Explainability Agent takes `EvaluationResult` + `ScoringResult` + action text
directly — no `ContextPackage`, no `AgentInput`. Locked rule from
`reference/CLAUDE.md`: "Explainability skips retrieval. Works only from
cached EvaluationResult." No DB queries, no `get_context_package` call.

### 2. Input shape mirrors `/capa/improve`'s eval resolution, not a new path

`POST /capa/explain` resolves `(EvaluationResult, RecurrenceResult)` exactly
like `/capa/improve` already does: `_resolve_action_text()` → check
`eval_cache.get()` → on miss, run `evaluator.run()` fresh and populate the
cache. Then `scoring_engine.compute_score(evaluation, recurrence)` to get the
`ScoringResult` (score/weakness_level/failed_dimensions) the agent needs —
this is a deterministic Python recompute, not a second LLM-touching agent
call, so doing it unconditionally (even on a cache hit) is free. No new
caching logic needed in this phase.

### 3. Output is `str`, not a Pydantic object — single deliberate exception

Every other agent in this build returns a validated Pydantic model. The
Explainability Agent returns a plain prose `str` by design — there's nothing
structured to validate (the contract is "under 120 words, no dimension
jargon, no JSON/markdown"), and forcing it through `call_llm_json` would mean
inventing a one-field wrapper schema for no benefit. Matches the reference's
`run() -> str` signature exactly. The API layer wraps it in
`ExplainActionResponse.explanation: str` for a validated envelope at the HTTP
boundary, same pattern every other route already uses.

### 4. Non-blocking: never raises, falls back to a deterministic string

Locked behavior from the reference (`explainability.py`'s `try/except`
around `call_llm`): on any LLM failure (all 3 fallback tiers exhausted,
timeout, etc.), return a fixed-template fallback string built from
`scoring_result.score`/`weakness_level`/`failed_dimensions[:3]` instead of
raising. This is the one agent in the build where an LLM failure does not
become a 502 — explanation text is advisory, not a decision-blocking output,
so degrading gracefully is the right call. Every other agent (`generator`,
`evaluator`, `improver`) raises `ValueError` on failure and the route
converts that to a 502; this agent's `run()` catches its own exceptions
internally and the route never needs a try/except around it.

### 5. `LIGHT_MODEL`, temp 0.4 — ported verbatim

Reference uses `LIGHT_MODEL` (`llama-3.1-8b-instant`) at temperature 0.4 for
this call — cheap, fast, appropriate for a single short prose generation
task on small structured input. No reason to deviate; `config.LIGHT_MODEL`
already exists and is otherwise unused in this build until now.

### 6. Prompt — ported with two changes for consistency with this build

`prompts/explainability/explain.jinja2` (own folder, matching the
`generator/`/`evaluator/`/`improver/` per-agent convention rather than the
reference's flat `prompts/explainability.jinja2`). Content is the reference
prompt almost verbatim (action text, score, weakness_level, failed
dimensions + reasons, recurrence warning if present → 3-4 sentences, <120
words, no dimension-name jargon, no bullets/JSON). Two changes:
- `org_name=config.ORG_NAME` added to the framing line (the
  "no hardcoded org name in prompts" rule applied to Generator/Evaluator/
  Improver in Phases 3b/4b/5 — `production.md` already flags this prompt as
  not yet audited; fixing it now closes that gap instead of leaving it open).
- Dimension names are title-cased via the same `replace("_", " ") | title`
  Jinja filter chain the reference used — kept, it already reads fine in
  prose form and there's no reason to hand-write a synonym map per dimension.

### 7. `POST /capa/explain` — new route, audit-only (no persistence)

Like `/capa/improve`, this never writes to `CAPA_ACTIONS` or
`capa_ai_evaluations` (nothing new to persist — the evaluation underneath it
was already persisted by `/capa/evaluate` if `action_id`-backed, or is
ad-hoc per Phase 4 decision 1, unchanged here). Always writes
`capa_ai_audit_trail` tagged `agent="explainability"`. Because `run()` never
raises, the route has no agent-failure branch — the audit write and 200
response always happen once the cache/eval resolution step succeeds (that
step *can* still raise `ValueError`, same 502 path as `/capa/improve`, since
it's the shared evaluator call, not the Explainability agent itself).

---

## Build plan

### Config (`config.py`)
- `EXPLAINABILITY_MODEL_VERSION = f"{LIGHT_MODEL}@{prompt_version(Path('explainability') / 'explain.jinja2')}"`
  — same pattern as the other 3 `*_MODEL_VERSION` constants.

### Schemas (`models/schemas.py`)
- `ExplainActionResponse` — `request_id`, `capa_id`, `action_id: Optional[str]`,
  `explanation: str`, `score: int`, `weakness_level: WeaknessLevel`,
  `model_version: str`. No new agent-output schema (per decision 3, the
  agent itself returns `str`).

### Prompts (`prompts/explainability/explain.jinja2`)
New folder + template per decision 6.

### Agent (`agents/explainability.py`)
`async def run(eval_result: EvaluationResult, scoring_result: ScoringResult, action_text: str) -> str`.
Builds `dim_reasons` dict from `ALL_DIMENSIONS` (same single-source-of-truth
pattern every other agent uses), renders the prompt, calls `call_llm` (not
`call_llm_json` — plain text, decision 3) with `config.LIGHT_MODEL` at temp
0.4, wrapped in try/except per decision 4 with the deterministic fallback
string on any exception.

### API (`api/routes.py`)
`POST /capa/explain` — resolve action text → resolve
`(evaluation, recurrence)` via the same cache-or-fresh-evaluate pattern as
`/capa/improve` (502 on `ValueError` from that step only) →
`scoring_engine.compute_score(evaluation, recurrence)` → `explainability.run(...)`
(never raises) → always `repo.write_audit(...)` tagged `agent="explainability"`
→ `ExplainActionResponse`.

### Tests
- `tests/unit/test_explainability.py` — mocked `call_llm`: prompt renders
  with `org_name`, only failed dimensions appear in `dim_reasons` usage
  (passing dims still computed into the dict but the prompt's `{% if %}`
  only lists `failed_dimensions` — verify the template doesn't leak passing
  dims into the failed-list section), recurrence_warning omitted when
  `recurrence_detected=False`, LLM-failure path returns the deterministic
  fallback string containing the score/weakness_level/top-3 failed
  dimensions, fallback never raises.
- `tests/unit/test_explain_route.py` — mocked agent/evaluator/repo: cache hit
  path skips `evaluator.run`, cache miss path calls it and populates the
  cache (reusing the existing `eval_cache` module — no new cache test needed,
  Phase 5's `test_eval_cache.py` already covers the cache itself), 404 on
  unknown `action_id`, 422 when neither `action_id` nor `actions[0]` given,
  502 only from the eval-resolution step (not from the agent, which cannot
  fail the route), audit always written, response score/weakness_level match
  `scoring_engine.compute_score`'s output.
- `tests/integration/test_explainability.py` — ground-truth-ish (no numeric
  ground truth like the Improver's "score must increase" — explanation
  quality is checked structurally, same spot-check style the reference used):
  N live weak seed actions → `/capa/evaluate` → `/capa/explain` → assert
  non-empty, ≤120 words (generous slack for live LLM variance — assert
  ≤180 as a hard ceiling, flag if it ever exceeds 150 in practice), no raw
  dimension snake_case tokens (`root_cause_linkage`, `effectiveness_check`,
  etc.) appear verbatim, no JSON braces/markdown bullets in the output.
  Self-skips if dev DB is down, matching every other integration suite.

---

## Implementation

**`config.py`** — `EXPLAINABILITY_MODEL_VERSION` (hash of
`prompts/explainability/explain.jinja2`, `LIGHT_MODEL`-prefixed like the
reference's model choice for this agent).

**`models/schemas.py`** — `ExplainActionResponse` (API envelope only; the
agent itself returns `str` per decision 3), added right after the Phase 5
Improver contracts.

**`prompts/explainability/explain.jinja2`** (new folder) — ported from the
reference almost verbatim, with `org_name=config.ORG_NAME` added to the
framing line (closes the one outstanding gap `production.md` had flagged:
"not yet audited for Improver/Explainability" — now audited for both).

**`agents/explainability.py`** (new) — `run(eval_result, scoring_result,
action_text) -> str`. Builds `dim_reasons` from `ALL_DIMENSIONS`, renders the
prompt, calls `call_llm` (not `call_llm_json` — plain prose, no schema) at
`config.LIGHT_MODEL`/temp 0.4, wrapped in try/except returning the
deterministic fallback string on any exception. Never imports
`agents.evaluator` — same separation every other agent keeps from eval
resolution, which is the route's job.

**`api/routes.py`** — factored `_resolve_evaluation(capa, agent_input,
action_text, repo)` out of `/capa/improve`'s inline cache-or-fresh-evaluate
logic (now shared by `/capa/improve` and the new `/capa/explain` — first
reuse of that specific block). New `POST /capa/explain`: resolves action text
→ `get_context_package(..., "evaluator", repo)` (cache-miss fallback needs
the evaluator's own retrieval config, not the explainability one, since
`RETRIEVAL_CONFIG["explainability"] = []`) → `_resolve_evaluation(...)` (502
only from this step, on a `ValueError` from `evaluator.run`) →
`scoring_engine.compute_score(...)` → `explainability.run(...)` (never
raises) → always `repo.write_audit(...)` tagged `agent="explainability"` →
`ExplainActionResponse`. No persistence beyond the audit row — nothing new
to write (same as `/capa/improve`).

**`phases/production.md`** — closed the "not yet audited for
Improver/Explainability" org-name item; both are now `{{ org_name }}`-driven.

### How to Run

```bash
conda activate capa-ai
cd service
uvicorn main:app --reload --port 8001
```

## How to Test (Checkpoint 6)

```bash
pytest tests/unit/test_explainability.py -v
pytest tests/unit/test_explain_route.py -v
pytest tests/integration/test_explainability.py -v
pytest tests/ -v
```

## Checkpoint 6 — PASSED

- [x] Unit suite green — 11 new tests (5 `test_explainability.py` + 6
      `test_explain_route.py`), full `tests/unit/` suite 213/213 passing,
      zero regressions on Phase 1-5 tests.
- [x] Integration spot-check — 2/2 live cases (`vague_training_only`,
      `no_owner`): evaluate weak action → explain → non-empty prose, under
      the 180-word ceiling, no raw dimension snake_case tokens, no
      JSON/markdown — against live Groq/OpenRouter + live DB + live ChromaDB.
- [x] `POST /capa/explain` route plumbing verified: cache hit skips
      `evaluator.run` entirely, cache miss runs it and populates the cache
      (shared `_resolve_evaluation` helper, also now used by `/capa/improve`),
      404 on unknown `action_id`, 422 when neither `action_id` nor
      `actions[0]` given, 502 only from the eval-resolution step (the
      Explainability agent itself cannot fail the route), audit always
      written, nothing ever persisted beyond the audit row.
- [x] Full suite (`pytest tests/ -v`) green end to end — 258/258 passing,
      no regressions on any prior phase's tests.
- [x] `phases/production.md` org-name audit item closed for Improver +
      Explainability.
