# Phase 5 — Improver Agent

Goal: given a weak CAPA action (flat text, same input shape as the Evaluator —
either an existing `CAPA_ACTIONS` row via `action_id`, or ad-hoc free text) plus
its `EvaluationResult`/`RecurrenceResult`, rewrite the action so every failed
dimension is resolved. This is the rewrite half of "Weak CAPA Detection" — the
Evaluator scores, the Improver fixes. Human-in-the-loop still holds: the
Improver never writes back to `CAPA_ACTIONS` — it only returns improved text
for a human to accept/edit/discard.

Reference build (`reference/backend/agents/improver.py`) has a finished version
of this, but it targets the reference's `requirements`/`options` shape (the
Generator's evolved output format). Our Evaluator deliberately decoupled from
that shape in Phase 4 decision 1 — it scores flat action text so it also works
on manually-written/legacy CAPA actions, not just Generator output. The
Improver inherits that same decoupling: input and output are both flat text,
not `requirements`/`options`.

---

## Decisions made this session

### 1. Input shape mirrors the Evaluator exactly, not the Generator

Same `action_id` / `actions[0]` resolution as `POST /capa/evaluate`
(`phases/phase4.md` decision 1). `CAPARecord.edit_instruction` (already
reserved on the schema — `# Improver only`) is rendered into the prompt when
present, so a human can steer the rewrite ("focus on the due date", "make the
evidence requirement stricter") without it being a required field.

### 2. Output is flat text, not `requirements`/`options`

`ImproverResult` = `original_action_text: str`, `improved_action_title: str`,
`improved_action_description: str`, `changes_explained: list[str]` (>=1 item,
plain language, one bullet per fixed gap). Concatenating
`improved_action_title + ": " + improved_action_description` must itself be
valid input to `POST /capa/evaluate`'s ad-hoc `actions[0]` path — that's the
phase's ground-truth test (improve a weak action, re-evaluate the improved
text, score must go up).

### 3. Eval cache — new, small, in `services/eval_cache.py`

CLAUDE.md's locked architectural rule (carried over from the reference):
*"Improver uses cached eval — if `EvaluationResult` exists in session, use it;
only run a fresh evaluation if no cache."* This build has no eval cache yet
(Phase 4 didn't need one — `/capa/evaluate` is terminal). Added now as its own
module rather than a route-local dict, because both `/capa/evaluate` (writer)
and `/capa/improve` (reader) need it and it's a distinct concern:

```python
# services/eval_cache.py
def make_key(tenant_id: str, capa_id: str, action_id: str | None, action_text: str) -> str
def get(key: str) -> tuple[EvaluationResult, RecurrenceResult] | None
def put(key: str, value: tuple[EvaluationResult, RecurrenceResult]) -> None
```

Bounded `OrderedDict` (`_MAX_ENTRIES = 200`, evict oldest on overflow) — same
"bounded LRU" fix the reference's own Phase 6 hardening pass made after
shipping an unbounded version (`analysis.md`'s caching findings). `get()`
moves the hit to the end (LRU touch). Key = `f"{tenant_id}:{capa_id}:{action_id or md5(action_text)}"`
— `action_id` is preferred when present (stable across calls even if the
action's text is later edited in the DB between calls is irrelevant — admin
re-evaluates explicitly to refresh).

`/capa/evaluate` writes to the cache after computing (in addition to its
existing `repo.write_evaluation`/`repo.write_audit` calls — the cache is purely
an in-process optimization, not a persistence path). `/capa/improve` checks
the cache first; on a miss it calls `evaluator.run()` directly (not over HTTP)
to get the same `(EvaluationResult, RecurrenceResult)` pair, then populates the
cache itself so a second `/improve` or a later `/evaluate` on the same action
within the process lifetime also hits.

### 4. Agent never calls the Evaluator itself

`agents/improver.py::run()` takes `eval_result`/`recurrence` as required
arguments — it does not import `agents.evaluator` or know about the cache.
Cache-or-fresh-evaluate resolution is the route's job (`api/routes.py`), same
separation `evaluator.py` keeps from `scoring_engine.py`. Keeps the agent
unit-testable with a hand-built `EvaluationResult` and no LLM/DB mocking for
that half of the input.

### 5. Single LLM call, own prompt folder

One call (`PRIMARY_MODEL`, temp 0.3 — higher than the Evaluator's 0.1 since
this is generative, not classification), `services/llm.py::call_llm_json()`
(already has retry-once-with-correction — no need to hand-roll the reference's
manual 2-attempt loop). New `prompts/improver/rewrite.jinja2`, self-contained
per the same reasoning as Evaluator's Sub-Phase 4b decision 2 (no shared
`prompts/_shared/` fragment library — a few duplicated lines beat cross-agent
coupling). Fed: original action text, only the *failed* dimension gaps (name +
reason — passing dimensions aren't gaps to fix), `edit_instruction` if given,
recurrence warning if present, problem_summary/root_cause/root_cause_category/
contributing_factors/missing_controls/severity/site_id from `ContextPackage`,
top-5 `effective_actions` (already filtered to closed+effective by
`fetch_effective_actions` upstream) and top-3 `relevant_sops` excerpts as
positive reference material, `org_name=config.ORG_NAME` (no hardcoded org
name, consistent with Generator/Evaluator).

### 6. Retrieval config

`config.RETRIEVAL_CONFIG["improver"] = ["sql", "vector"]` already exists from
Phase 2/3 setup — unchanged, no new retrieval work this phase.

### 7. No persistence of the improved text

Per the non-negotiable "human-in-the-loop, AI never submits/approves/closes a
CAPA" constraint: `POST /capa/improve` always writes a `capa_ai_audit_trail`
row (agent="improver") but never writes to `CAPA_ACTIONS` — the improved text
is returned to the caller for a human to accept (which would go through
whatever normal SoapBox action-edit path already exists, outside this
service's scope) or discard.

---

## Build plan

### Schemas (`models/schemas.py`)
- `ImproverResult` — `original_action_text: str`, `improved_action_title: str`,
  `improved_action_description: str`, `changes_explained: list[str]`
  (validator: >=1 item).
- `ImproveActionResponse` (API envelope) — `request_id`, `capa_id`,
  `action_id: Optional[str]`, `original_action_text`, `improved_action_title`,
  `improved_action_description`, `changes_explained`, `model_version`.

### New module — `services/eval_cache.py`
`make_key()`, `get()`, `put()` as in decision 3. Pure in-memory, no DB. Unit
tested in isolation (no LLM/DB needed).

### Config (`config.py`)
`IMPROVER_MODEL_VERSION = f"{PRIMARY_MODEL}@{prompt_version(Path('improver') / 'rewrite.jinja2')}"`.
`EVAL_CACHE_MAX_ENTRIES = 200` (named constant, not a literal in
`eval_cache.py` — consistent with the "no hardcoded literals" rule already
applied to `RECURRENCE_PENALTIES` in Phase 4).

### Prompts (`prompts/improver/rewrite.jinja2`)
Single self-contained template per decision 5.

### Agent (`agents/improver.py`)
`async run(agent_input: AgentInput, eval_result: EvaluationResult, recurrence: RecurrenceResult) -> ImproverResult`.
Builds the failed-gaps list from `ALL_DIMENSIONS` (reuses the existing single
source of truth, same pattern the reference used), renders the prompt, calls
`call_llm_json` against a small internal `_ImproverLLMResult` schema
(`improved_action_title`, `improved_action_description`, `changes_explained`),
wraps into `ImproverResult` with `original_action_text` attached.

### API (`api/routes.py`)
`POST /capa/improve` — resolve `action_text` from `action_id`/`actions[0]`
(same logic as `/capa/evaluate`, factor into a shared helper
`_resolve_action_text(capa, repo) -> tuple[str, str | None]` since it's now
used twice — first real cross-route reuse this build has needed); cache lookup
via `services.eval_cache`; on miss call `evaluator.run()` directly + populate
cache; call `improver.run(...)`; 502 on agent `ValueError`; always
`repo.write_audit(...)` tagged `agent="improver"`; no `repo.write_evaluation`
call (nothing new to persist — the cached/just-computed evaluation was either
already persisted by a prior `/evaluate` call or is this call's own ad-hoc,
non-persisted computation per Phase 4 decision 1, unchanged here).
`POST /capa/evaluate` gets one addition: write to `eval_cache.put(...)` after
scoring.

### Tests
- `tests/unit/test_eval_cache.py` — put/get round-trip, LRU eviction at
  `EVAL_CACHE_MAX_ENTRIES + 1`, miss returns `None`, key collision behavior
  (same tenant/capa/action_id always same key regardless of text).
- `tests/unit/test_improver.py` — mocked `call_llm_json`: gaps list only
  contains failed dimensions, `edit_instruction` flows into the rendered
  prompt, schema validation retry path, `ImproverResult.changes_explained`
  non-empty enforced.
- `tests/unit/test_improve_route.py` — mocked agent/evaluator/repo: cache hit
  path skips `evaluator.run`, cache miss path calls it and populates the
  cache, 404 on unknown `action_id`, 422 when neither `action_id` nor
  `actions[0]` given, 502 on agent failure, audit always written.
- `tests/integration/test_improver.py` — **ground-truth test**: take N weak
  seed actions (low/critical `weakness_level` from a live `/capa/evaluate`
  call), improve each, re-evaluate the improved text via a second live
  `/capa/evaluate` call, assert improved score > original score for every
  case. Self-skips if dev DB is down, matching every other integration suite.

---

## Implementation

**`models/schemas.py`** — `ImproverResult` (`original_action_text`,
`improved_action_title`, `improved_action_description`, `changes_explained`
with a >=1-entry validator) and `ImproveActionResponse` (API envelope), added
right after the Phase 4 evaluator contracts.

**`config.py`** — `IMPROVER_MODEL_VERSION` (hash of `prompts/improver/rewrite.jinja2`),
`EVAL_CACHE_MAX_ENTRIES = 200`.

**`services/eval_cache.py`** (new) — `make_key()`/`get()`/`put()` over a
module-level `OrderedDict`, exactly as decision 3 specced. `get()` does an LRU
touch (`move_to_end`); `put()` evicts the oldest entry past
`config.EVAL_CACHE_MAX_ENTRIES`.

**`prompts/improver/rewrite.jinja2`** (new) — single self-contained template;
takes the original action text, only the *failed* dimension gaps (name +
reason), `edit_instruction` if present, `recurrence_warning` if present, the
usual `ContextPackage` fields, top-5 `effective_actions` + top-3
`relevant_sops` as positive reference material, `org_name=config.ORG_NAME`.

**`agents/improver.py`** (new) — `run(agent_input, eval_result, recurrence) ->
ImproverResult`. Builds the failed-gaps list via `ALL_DIMENSIONS` (same single
source of truth the Evaluator uses), renders the prompt, single
`call_llm_json()` call (temp 0.3) against an internal `_ImproverLLMResult`
schema, wraps the result with `original_action_text` attached. Never imports
`agents.evaluator` — per decision 4, eval resolution is entirely the route's
job.

**`api/routes.py`** — factored `_resolve_action_text(capa, repo)` out of
`evaluate_action` (now used by both `/capa/evaluate` and `/capa/improve` —
first real cross-route helper this build has needed). `/capa/evaluate` now
also writes to `eval_cache.put(...)` right after `scoring_engine.compute_score`.
New `POST /capa/improve`: resolves action text → `get_context_package(...,
"improver", repo)` → `eval_cache.get(...)`, and only calls `evaluator.run()`
directly (not over HTTP) on a cache miss, populating the cache itself →
`improver.run(...)` → 502 on agent `ValueError` → always `repo.write_audit(...)`
tagged `agent="improver"` → `ImproveActionResponse`. No `repo.write_evaluation`
or any write to `CAPA_ACTIONS` — per decision 7, the AI never writes back; a
human accepts/discards the improved text outside this service.

### How to Run

```bash
conda activate capa-ai
cd service
uvicorn main:app --reload --port 8001
```

### How to Test (Checkpoint 5)

```bash
pytest tests/unit/test_eval_cache.py -v       # 7 tests — pure in-memory LRU, no LLM/DB
pytest tests/unit/test_improver.py -v         # 5 tests — agent logic, mocked LLM
pytest tests/unit/test_improve_route.py -v    # 6 tests — route plumbing, mocked agents
pytest tests/integration/test_improver.py -v  # 4 tests — ground truth: improved score > original
pytest tests/ -v                              # full suite
```

## Checkpoint 5 — PASSED

- [x] Unit suite green — 18 new tests (7 eval_cache + 5 improver + 6 improve_route),
      full `tests/unit/` suite 199/199 passing, zero regressions on Phase 1-4 tests.
- [x] Integration ground-truth test — 4/4 live cases (`vague_training_only`,
      `training_only_on_equipment_fault`, `no_owner`, `no_due_date_no_evidence`):
      evaluate weak action → improve → re-evaluate improved text → improved
      score strictly exceeds original score in every case, against live
      Groq/OpenRouter + live DB + live ChromaDB.
- [x] `POST /capa/improve` route plumbing verified: cache hit skips
      `evaluator.run` entirely, cache miss runs it and populates the cache,
      404 on unknown `action_id`, 422 when neither `action_id` nor
      `actions[0]` given, 502 on agent failure, audit always written,
      nothing ever written to `CAPA_ACTIONS`.
- [x] Full suite (`pytest tests/ -v`) green end to end, no regressions on any
      prior phase's tests.

---

## Sub-Phase 5b — Improve-then-supplement behavior + eval persistence Q&A

A user review pass after Checkpoint 5 raised two things: (1) how the locked
"Improver uses cached eval" rule actually holds up across production
replicas, and (2) a behavioral gap — the Improver only ever rewrote the
single original action, with no path to say "this one action structurally
cannot cover the root cause, something else needs to exist alongside it."

### Q&A — eval persistence in production

Answered and written up in full in `phases/production.md`'s new "Evaluator →
Improver eval persistence" section (don't duplicate the detail here, that
file is the source of truth for production-readiness gaps). Summary: the
`action_id` path is already durably persisted via `repo.write_evaluation()`
into `capa_ai_evaluations` independent of the cache; the ad-hoc `actions[0]`
path is **never** persisted anywhere (Phase 4 decision 1) — `eval_cache` is
the only copy, process-local. `/capa/improve`'s existing cache-miss fallback
(re-run `evaluator.run()`) is correct but wasteful under multi-replica
deployment. Not fixed this round — `capa_ai_evaluations` has no column to
reconstruct `RecurrenceResult` from, so a partial fix (read the DB row, fake
an empty recurrence) was rejected as worse than re-evaluating. Real fix
(shared Redis cache, and/or a `recurrence_result` column) is a `production.md`
item, not implemented here.

### Decision — improve-first, then supplement when structurally insufficient

User-specified behavior: the Improver should (1) always try to fix the
existing action by editing it, and (2) only when that's not enough on its
own, additionally suggest new actions — never instead of the improved
original, never as a replacement.

**Trigger is Python, not the LLM** (same anchor pattern as Evaluator's Phase
4 decision 2): `needs_additional_actions = not (root_cause_linkage.passed and
preventive_value.passed and training_overreliance.passed)` — these are
exactly the 3 dimensions the Evaluator itself derives objectively from
`action_theme`/`root_cause_category` via `config.CONTROL_STRENGTH_RUBRIC`/
`ROOT_CAUSE_CATEGORY_THEME_MAP`/`TRAINING_SUFFICIENT_CATEGORIES` — reusing
them here means "does this action structurally cover the root cause" has one
definition across both agents, not two. The LLM is told *why* the trigger
fired (the 3 dimensions' `reason` strings) and asked to produce
`additional_actions` only when it did; **Python still gates the output**
(`result.additional_actions[:_MAX] if needs_additional_actions else []`) even
if the LLM returns suggestions unprompted — the objective check, not the
model, has final say.

**Shape — reuses `GeneratedAction` verbatim** (user's explicit choice over a
lighter `{title, description, rationale}` shape): each additional action is a
full `requirements`/`options`/owner/due-date/evidence/confidence object,
identical to what `POST /capa/generate` produces. Capped at
`agents.improver._MAX_ADDITIONAL_ACTIONS = 2`. Validated by the same
`GeneratedAction` pydantic model (mandatory-exactly-1-option /
optional-2-to-5-options / required_evidence>=2 validators all apply
unchanged) — `call_llm_json`'s existing retry-once-with-correction handles a
validation failure on this nested shape the same way it already does for the
top-level object.

**One deliberate scope cut**: `agents/generator.py::_validate_due_date_windows()`
is *not* invoked on `additional_actions` — these are supplementary
suggestions for human review, not a primary generated action, and wiring two
agents' validation together for a non-primary output wasn't judged worth the
coupling. The prompt states the due-date windows for guidance; nothing
enforces them in code for this field. Revisit if additional_actions start
shipping with out-of-window dates often enough to matter.

### Build plan

- `models/schemas.py` — `ImproverResult.additional_actions: list[GeneratedAction] = []`,
  same field on `ImproveActionResponse`.
- `agents/improver.py` — `_ImproverLLMResult.additional_actions: list[GeneratedAction] = []`;
  `needs_additional_actions`/`structural_gap_reasons` computed in `run()`;
  `_ACTION_TYPES`/`_MAX_ADDITIONAL_ACTIONS` module constants; Python-side gate
  on the returned list before constructing `ImproverResult`.
- `prompts/improver/rewrite.jinja2` — new TASK 1 (always improve original) /
  TASK 2 (conditional, only rendered content differs — `additional_actions`
  key is always in the output JSON shape, empty when not needed) split,
  mirroring `prompts/generator/skeleton.jinja2`'s requirements-shape
  instructions inline (still self-contained, no shared fragment — unchanged
  reasoning from the original Sub-Phase 4b/5 decision).
- `api/routes.py` — `ImproveActionResponse(..., additional_actions=result.additional_actions)`
  one-line addition to the existing response construction.
- `phases/production.md` — new section (see Q&A above).

### Tests

- `tests/unit/test_improver.py` — 3 new tests: structural-gap trigger passes
  `additional_actions` through and caps at `_MAX_ADDITIONAL_ACTIONS`; no
  structural gap drops any LLM-returned suggestions (Python gate, not LLM
  compliance); reason strings for the 3 trigger dimensions appear in the
  rendered prompt.
- `tests/integration/test_improver.py` — extended the existing 4-case
  ground-truth test: asserts `len(additional_actions) <= _MAX_ADDITIONAL_ACTIONS`
  always, and `additional_actions == []` when the structural trigger didn't
  fire. No hard minimum asserted on the trigger-fired side (LLM compliance
  with the *request* for suggestions is not deterministic — only the gate is;
  asserting a hard minimum would make the live suite flaky).

### Checkpoint 5b — PASSED

- [x] Unit suite green — 202/202 (3 new improver tests), no regressions.
- [x] Integration suite green — 4/4 live cases, `additional_actions` bound
      respected and gate verified on every case, against live Groq/OpenRouter
      + live DB + live ChromaDB.
- [x] `phases/production.md` updated with the eval-persistence Q&A.

### How to Test (Checkpoint 5b)

```bash
pytest tests/unit/test_improver.py -v          # 8 tests total now
pytest tests/integration/test_improver.py -v   # 4 tests, extended assertions
pytest tests/ -v                               # full suite
```
