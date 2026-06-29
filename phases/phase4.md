# Phase 4 — Evaluator / Scoring Engine

Goal: given a `CAPARecord` + an action (either an existing `CAPA_ACTIONS` row via
`action_id`, or ad-hoc free text), score it deterministically across 9 weighted
dimensions, classify a weakness level, and flag recurrence. This is the "Weak CAPA
Detection" capability. Non-negotiable: **LLM never scores** — scoring is deterministic
Python; the LLM only does semantic judgment/classification that Python then reads
deterministically.

Reference build (`reference/backend/engines/scoring_engine.py` +
`reference/backend/agents/evaluator.py`) has a finished 3-layer version of this. We port
the 3-layer structure but strengthen 4 real gaps found in it during review (not ported
as-is — see decisions below).

---

## Decisions made this session

### 1. Evaluator input — flat action text, not `GeneratedAction`

User decision: Evaluator scores flat existing CAPA action text — the original "Weak CAPA
Detection" use case, decoupled from the Generator (works on manually-written/legacy CAPA
actions too, not just freshly generated ones).

`CAPARecord` gets a new `action_id: Optional[str]`. If given, the evaluator resolves the
real `CapaAction` row via `repo.fetch_actions()` (already exists) and evaluates its
title+description; the result is persisted via `repo.write_evaluation()` (already
exists, FK's to `CAPA_ACTIONS.ACTION_ID`). If only free-text `CAPARecord.actions` is
given (no `action_id`), it's an ad-hoc evaluation — scored, not persisted (no FK target).
`AgentInput.action_text: Optional[str]` carries the resolved text into the agent.

### 2. Four gaps fixed relative to the reference build

The reference's evaluator was checked against actual shipped code (not just `plan.md`'s
draft), per CLAUDE.md's "check the code, not just the doc" rule. Four real gaps were
found on review and fixed here rather than ported as-is:

**(a) `root_cause_linkage` had no objective anchor — was 100% LLM judgment.**
**(b) `preventive_value` was a bare LLM pass/fail — no rubric.**

Fixed together: we already have `CAPA_AI_ACTION_TAXONOMY` (10 distinct `THEME` values:
SOP Update, Engineering Control, Signage, PPE, Training, Inspection Cadence, Maintenance
Schedule, Process Change, Personnel Change, System/Software Control) and `CAPA_CATEGORIES`
(8 root-cause categories, confirmed via `seeds/data/categories.json`/`rca.json` that
`ContextPackage.root_cause_category` carries the `CATEGORY_ID` string, e.g.
`CAT_EQUIPMENT_FAULT`, not the display name). These become the objective anchor:

- `config.CONTROL_STRENGTH_RUBRIC` — `theme -> strength score 0-100`, hierarchy-of-
  controls ordered (Training 40 ... Engineering Control 90, System/Software Control 95).
- `config.ROOT_CAUSE_CATEGORY_THEME_MAP` — `category_id -> set of compatible themes`,
  all 8 categories mapped.
- `config.TRAINING_SUFFICIENT_CATEGORIES = {"CAT_TRAINING_GAP"}` — the one category
  where a pure-Training action is the systemic fix, not overreliance.
- `config.PREVENTIVE_VALUE_PASS_THRESHOLD = 60`.

The LLM's role narrows to *classification* (`action_theme`, one of the 10 themes) and
*one semantic fact* (`addresses_root_cause`: does the action's substance, not just its
label, address the cited contributing factors/missing controls). Python derives all 3
dimensions from that + the config tables — the LLM never says `passed` for any of them:

```
root_cause_linkage.passed   = addresses_root_cause AND action_theme in ROOT_CAUSE_CATEGORY_THEME_MAP[category]
preventive_value.passed     = CONTROL_STRENGTH_RUBRIC[action_theme] >= PREVENTIVE_VALUE_PASS_THRESHOLD
training_overreliance.passed = action_theme != "Training" OR category in TRAINING_SUFFICIENT_CATEGORIES
```

**(c) Recurrence only matched exact `root_cause_category` string — too coarse, no
same-site signal.**

Fixed by reuse instead of new SQL: `ContextPackage.similar_capas` (Phase 2) is already
vector+SQL merged, ranked, capped at `config.MAX_SIMILAR_CAPAS`, and vector hits already
passed `config.VECTOR_SIMILARITY_THRESHOLD` — i.e. it's already metadata-filtered +
semantically-matched similar-CAPA data, not a raw category count. Layer 3 filters
`similar_capas` down to entries matching the current `root_cause_category` for
`prior_occurrence_count`, and adds `RecurrenceResult.recurred_at_same_site: bool` by
comparing those entries' `site_id` to the current CAPA's (no new repo/SQL — both fields
already exist on `SimilarCapaSummary`). Full past-action text for the "is this the same
fix as before" LLM comparison reuses the already-existing
`repo.fetch_actions_bulk(tenant_id, capa_ids)` — **no new repository methods needed at
all** for recurrence.

**(d) Penalties (`-15`, `-5`) were hardcoded in `scoring_engine.py`.**

Fixed: `config.RECURRENCE_PENALTIES` — a named dict (`same_approach_failed`,
`same_approach_unknown`, `comparison_unavailable`, `new_approach_failed_category`) —
`scoring/engines/scoring_engine.py` reads from it, never a literal.

### 3. Layer/call split

- **Layer 1** (pure regex, no LLM): `ownership`, `due_date_quality`,
  `evidence_requirement`, `effectiveness_check` — ported from reference's tightened
  rules (e.g. ownership requires "assigned to"/role-noun, not bare team name).
- **Layer 2 Call A** (LLM, temp 0.1, `evaluator_structural.jinja2`): `clarity`,
  `specificity` only — pure wording judgments, no taxonomy needed.
- **Layer 2 Call B** (LLM, temp 0.1, `evaluator_classify.jinja2`): `action_theme` +
  `addresses_root_cause` (+ reason) — feeds root cause, contributing/missing controls,
  top-5 similar CAPAs. Python derives `root_cause_linkage`/`preventive_value`/
  `training_overreliance` from this per decision 2.
- **Layer 3 recurrence** (`evaluator_recurrence.jinja2`): only called if
  `prior_occurrence_count >= 1` (from the `similar_capas` filter above); compares current
  action text against full past-action text (`fetch_actions_bulk`) +
  effectiveness (`verified_date IS NOT NULL` => "Verified") → `new_actions_are_same_as_past`
  / `past_actions_were_effective` / `recurrence_warning`.
- Call A, Call B, and the recurrence call all run concurrently via
  `asyncio.gather(..., return_exceptions=True)`. Fail-closed: an exception in Call A
  fails `clarity`/`specificity` closed; an exception in Call B fails
  `root_cause_linkage`/`preventive_value`/`training_overreliance` closed (`action_theme`
  unresolved => treated as not in any compatible set, not in rubric => 0 strength).
- Uses `services.llm.call_llm_json()` (already built, has its own retry-once-with-
  correction-prompt behavior) rather than re-implementing retry logic per call.

### 4. Scoring stays a separate pure-Python module

`engines/scoring_engine.py` (the `engines/` package already exists, empty, scaffolded
for this — matches the reference's own layout). `compute_score(eval_result,
recurrence) -> ScoringResult`: sums `weight*100` per passed dimension
(`config.DIMENSION_WEIGHTS`), applies one `config.RECURRENCE_PENALTIES` branch, clamps
≥0, rounds, maps to `config.WEAKNESS_THRESHOLDS`. No LLM import in this file at all —
independently unit-testable.

---

## Build plan

### Schemas (`models/schemas.py`)
- `ActionTheme` (`Literal`, 10 taxonomy themes), `WeaknessLevel` (`Literal`, 5 tiers)
- `DimensionResult` (`passed: bool`, `reason: str`)
- `EvaluationResult` (9 named `DimensionResult` fields — `training_overreliance`
  docstring notes inverted semantics)
- `ALL_DIMENSIONS = list(EvaluationResult.model_fields.keys())` — single source, no
  per-file duplication
- `RecurrenceResult` (+ `recurred_at_same_site`), `ScoringResult`,
  `EvaluateActionResponse` (API envelope)
- `CAPARecord.action_id`, `AgentInput.action_text` additions

### DB / Repository
None — decision 2(c) above replaces both planned new repo methods with reuse of
`ContextPackage.similar_capas` + the existing `fetch_actions_bulk`.

### Config (`config.py`)
`DIMENSION_WEIGHTS`, `WEAKNESS_THRESHOLDS`, `CONTROL_STRENGTH_RUBRIC`,
`ROOT_CAUSE_CATEGORY_THEME_MAP`, `TRAINING_SUFFICIENT_CATEGORIES`,
`PREVENTIVE_VALUE_PASS_THRESHOLD`, `RECURRENCE_PENALTIES`,
`EVALUATOR_MODEL_VERSION = f"{PRIMARY_MODEL}@{prompt_version('evaluator_structural.jinja2', 'evaluator_classify.jinja2', 'evaluator_recurrence.jinja2')}"`.

### Prompts (`prompts/`)
`evaluator_structural.jinja2` (Call A), `evaluator_classify.jinja2` (Call B),
`evaluator_recurrence.jinja2` (Layer 3) — adapted to `ContextPackage` field names like
`prompts/generator/` was (no resolved site/department name strings). Note: Generator's prompt
was a single `generator.jinja2` when this was written; Phase 3 Sub-Phase 3b later split it into
`prompts/generator/{skeleton,enrich}.jinja2` — see `phases/phase3.md`.

### Scoring engine (`engines/scoring_engine.py`)
`compute_score(eval_result: EvaluationResult, recurrence: RecurrenceResult) -> ScoringResult`.

### Agent (`agents/evaluator.py`)
`async run(agent_input: AgentInput, repo: CapaRepository) -> tuple[EvaluationResult, RecurrenceResult]`.
Layer 1 regex helpers; `_call_a`/`_call_b`/`_recurrence_check` via `call_llm_json`;
`asyncio.gather` to run them concurrently; assembles `EvaluationResult`.

### API (`api/routes.py`)
`POST /capa/evaluate` — body `CAPARecord` (+ optional `action_id`) →
resolve action text (via `repo.fetch_actions` if `action_id` given, else
`capa_input.actions[0]`) → `get_context_package(..., "evaluator", repo)` →
`evaluator.run(...)` → `scoring_engine.compute_score(...)` → 502 on agent `ValueError` →
`repo.write_evaluation(...)` only if `action_id` given → always `repo.write_audit(...)`
→ `EvaluateActionResponse`.

### Tests
- `tests/unit/test_scoring_engine.py` — weight sums, recurrence penalty branches (via
  `config.RECURRENCE_PENALTIES`), threshold boundaries, clamping.
- `tests/unit/test_evaluator_layer1.py` — regex edge cases for the 4 Layer-1 dimensions.
- `tests/unit/test_evaluator_classification.py` — theme x category -> dimension triple,
  pure Python, no LLM/network.
- `tests/unit/test_evaluate_route.py` — mocked agent/context/repo: status codes, audit
  write, persistence-only-when-`action_id` branch.
- `tests/integration/test_evaluator.py` — live LLM+DB+vector, ~10 cases (strong/weak/
  training-only-on-non-training-category/no-owner/recurrence-flagged-same-site/
  recurrence-flagged-different-site), self-skips if dev DB down.

---

## Implementation

**`models/schemas.py`** — `ActionTheme` (Literal, 10 taxonomy themes), `WeaknessLevel`
(Literal, 5 tiers), `DimensionResult`, `EvaluationResult` (9 fields), `ALL_DIMENSIONS`,
`RecurrenceResult` (+ `recurred_at_same_site`), `ScoringResult`, `EvaluateActionResponse`;
`CAPARecord.action_id`, `AgentInput.action_text` additions.

**`config.py`** — `DIMENSION_WEIGHTS`, `WEAKNESS_THRESHOLDS`, `CONTROL_STRENGTH_RUBRIC`,
`ROOT_CAUSE_CATEGORY_THEME_MAP` (all 8 categories), `TRAINING_SUFFICIENT_CATEGORIES`,
`PREVENTIVE_VALUE_PASS_THRESHOLD`, `RECURRENCE_PENALTIES`, `EVALUATOR_MODEL_VERSION`.

**`prompts/evaluator_structural.jinja2`** (Call A: clarity/specificity only),
**`evaluator_classify.jinja2`** (Call B: classifies `action_theme` + judges
`addresses_root_cause`, fed the taxonomy theme list + root cause + contributing/missing
controls + top-5 similar CAPAs), **`evaluator_recurrence.jinja2`** (compares new action
text against full past-action text + effectiveness signal).

**`engines/scoring_engine.py`** — `compute_score(eval_result, recurrence) ->
ScoringResult`. No LLM import. `_recurrence_penalty()` reads `config.RECURRENCE_PENALTIES`
by name (no literals); explicitly handles `new_actions_are_same_as_past is None` as its
own `comparison_unavailable` penalty branch (the silent-disable bug `analysis.md` flagged
in the reference build cannot recur here — there's a dedicated test for it).

**`agents/evaluator.py`** — `run(agent_input, repo) -> (EvaluationResult,
RecurrenceResult)`. Layer 1 (`_rule_based`) ports the reference's tightened regex
patterns verbatim for `ownership`/`due_date_quality`/`evidence_requirement`/
`effectiveness_check`. Layer 2 Call A/Call B and Layer 3 recurrence all use
`services.llm.call_llm_json()` (already built — has its own retry-once-with-correction
behavior) rather than re-implementing retry logic. `_derive_from_classification()` is
pure Python — given Call B's `action_theme`+`addresses_root_cause`, it looks up
`config.ROOT_CAUSE_CATEGORY_THEME_MAP`/`CONTROL_STRENGTH_RUBRIC`/
`TRAINING_SUFFICIENT_CATEGORIES` to produce all 3 derived dimensions; the LLM never
asserts `passed` for them. `_recurrence_check()` filters
`agent_input.context_package.similar_capas` by `root_cause_category` (no new SQL — reuses
Phase 2's already vector+structural-merged data), flags `recurred_at_same_site` by
comparing `site_id`, and only makes the comparison LLM call if at least one prior
occurrence was found (fetching full past-action text via the already-existing
`repo.fetch_actions_bulk`). Call A, Call B, and recurrence run concurrently via
`asyncio.gather(..., return_exceptions=True)`; each failure mode fails its own
dimensions closed independently.

**`api/routes.py`** — `POST /capa/evaluate`: resolves `action_text` from `action_id`
(via `repo.fetch_actions`, 404 if not found) or `actions[0]` (422 if neither given) →
`get_context_package(..., "evaluator", repo)` → `evaluator.run(...)` →
`scoring_engine.compute_score(...)` → 502 on agent `ValueError` → `repo.write_evaluation`
only when `action_id` was given (ad-hoc text evaluations have no `CAPA_ACTIONS` row to
FK against) → always `repo.write_audit` tagged `agent="evaluator"` →
`EvaluateActionResponse`.

**Live finding during testing:** one *pre-existing* (Phase 3) integration test
(`test_generator.py::test_generator_checkpoint[containment]`) failed during this phase's
full-suite run — Groq quota exhausted, OpenRouter's free-tier model returned a response
with `content: null`, and `services/llm.py:strip_fences()` doesn't guard against `None`.
Same documented quota-pressure pattern as Phase 3's own checkpoint note, not a Phase 4
regression — `agents/evaluator.py` doesn't touch `strip_fences` at all (uses
`call_llm_json`). Left as-is; worth a small defensive fix in `services/llm.py` in a later
hardening pass, out of scope here.

### How to Run

```bash
conda activate capa-ai
cd service
uvicorn main:app --reload --port 8001
```

### How to Test (Checkpoint 4 — PASSED)

```bash
pytest tests/unit/test_scoring_engine.py -v             # 20 tests — pure math, no LLM
pytest tests/unit/test_evaluator_layer1.py -v            # 14 tests — regex edge cases
pytest tests/unit/test_evaluator_classification.py -v    # 85 tests — theme x category derivation, no LLM
pytest tests/unit/test_evaluate_route.py -v               # 5 tests — route plumbing (mocked)
pytest tests/integration/test_evaluator.py -v             # 5 tests — live Groq/OpenRouter + live DB + live ChromaDB
pytest tests/ -v                                          # full suite
```

## Checkpoint 4 — PASSED

- [x] Unit suite green — 124 new tests (20 scoring engine + 14 layer1 + 85 classification +
      5 route), full `tests/unit/` suite 179/179 passing, zero regressions on Phase 1-3 tests.
- [x] Integration suite — 5/5 live cases (`strong_engineering_control`,
      `weak_vague_training_only`, `training_only_on_equipment_fault`, `no_owner`,
      `training_sufficient_for_training_gap`) against live Groq/OpenRouter + live DB +
      live ChromaDB.
- [x] `POST /capa/evaluate` route plumbing verified: `action_id` path persists +
      writes audit, ad-hoc `actions[0]` path scores without persisting, 404 on unknown
      `action_id`, 422 when neither given, 502 on evaluator failure.
- [x] `grep -rln "SELECT \|INSERT INTO\|UPDATE \|DELETE FROM" --include="*.py" .` →
      unchanged exemption set (`models/schemas.py` docstring mention, `repositories/postgres.py`,
      `retrieval/nl2sql.py`, `seeds/load_seed.py`, plus the 2 expected test files) —
      `agents/evaluator.py` and `engines/scoring_engine.py` contain zero raw SQL.

---

## Sub-Phase 4b — Prompt genericization + folder restructure

A user review pass (after Phase 4's checkpoint and after Generator's own Sub-Phase 3b
restructure — see `phases/phase3.md`) raised the same two structural points the
Generator templates had already been fixed for, but the Evaluator's hadn't: (1) its 3
prompts hardcoded `"AcerTech Industries"` instead of `config.ORG_NAME`, and (2) they sat
as flat files directly in `prompts/`, unlike Generator's per-agent `prompts/generator/`
folder. Also asked directly: does recurrence actually penalize an action that repeats a
past, known-ineffective approach?

### Answering the recurrence question first

Yes — this was already wired in at Phase 4's first pass, unchanged here.
`engines/scoring_engine.py::_recurrence_penalty()` reads `recurrence.new_actions_are_same_as_past`
+ `recurrence.past_actions_were_effective` (both populated by the
`evaluator/recurrence.jinja2` LLM comparison call) and applies
`config.RECURRENCE_PENALTIES["same_approach_failed"]` (`-15`, the heaviest penalty) when
an action repeats a past approach that's on record as not having worked. Covered by
`tests/unit/test_scoring_engine.py::test_recurrence_same_approach_failed_applies_heaviest_penalty`.
Nothing changed here this round — only the prompt's wording/location changed, not the
scoring logic.

### Decisions

**1. Folder structure mirrors `prompts/generator/`.** New `prompts/evaluator/` with 3
top-level call prompts (`structural.jinja2`, `classify.jinja2`, `recurrence.jinja2` — no
`evaluator_` prefix needed, the folder is the namespace, same convention as
`generator/skeleton.jinja2`) plus 3 shared fragments (`_action_text.jinja2`,
`_capa_context.jinja2`, `_root_cause_context.jinja2`). Old flat
`prompts/evaluator_structural.jinja2`/`evaluator_classify.jinja2`/`evaluator_recurrence.jinja2`
deleted (fully superseded).

**2. Evaluator's fragments are self-contained, not shared with Generator's.** Asked the
user directly: Generator's `_capa_context.jinja2` (problem_summary/root_cause/severity/
site_id/missing_controls) is nearly the same shape the Evaluator's `classify.jinja2`
needs. Decided **not** to promote a shared `prompts/_shared/` fragment — Evaluator gets
its own small fragments. Reasons: zero risk to Generator's already-checkpointed
Sub-Phase 3b code/hash, and the per-agent-folder intent in `phases/phase3.md`
decision 3/Sub-Phase 3b was literally "one folder per agent," not "one shared library."
The duplication is a handful of lines, not worth the cross-agent coupling.

**3. `org_name=config.ORG_NAME`** now passed into all 3 `template.render()` calls in
`agents/evaluator.py`, same pattern as `agents/generator.py`. `recurrence.jinja2` also
takes it (the reference's recurrence prompt said "before at AcerTech" — genericized to
"before at {{ org_name }}").

**4. `config.EVALUATOR_MODEL_VERSION`** rehashed over the 3 new paths via
`prompt_version(Path('evaluator') / 'structural.jinja2', ...)` — same `Path`-based call
shape `GENERATOR_MODEL_VERSION` already established, so `prompt_version()` didn't need
any changes.

### Build plan

- `prompts/evaluator/_action_text.jinja2`, `_capa_context.jinja2`,
  `_root_cause_context.jinja2`, `structural.jinja2`, `classify.jinja2`,
  `recurrence.jinja2` — new. Old flat 3 files deleted.
- `config.py` — `EVALUATOR_MODEL_VERSION` rehashed over the new paths.
- `agents/evaluator.py` — `_call_a`/`_call_b`/`_recurrence_check` updated to the new
  template paths + `org_name=config.ORG_NAME`.
- No schema/scoring-logic changes — this round is prompt structure + genericization only.

### Checkpoint 4b — PASSED

- [x] Unit suite green — 182/182, no regressions.
- [x] Integration suite green — 5/5 live cases against the restructured/genericized
      prompts.
- [x] `grep -ril "acertech" prompts/evaluator/` returns nothing — org name is not
      hardcoded anywhere in the new templates.
- [x] `grep -rln "SELECT \|INSERT INTO\|UPDATE \|DELETE FROM" --include="*.py" .` →
      unchanged exemption set.
- [x] `phases/production.md`'s org-name item updated to mark the Evaluator as audited
      (was previously flagged "not yet audited for other agents").

### How to Test (Checkpoint 4b — passed)

```bash
pytest tests/unit -q                            # 182 passed — no regressions
pytest tests/integration/test_evaluator.py -v   # 5 tests — live Groq + live DB + live ChromaDB
```

---
