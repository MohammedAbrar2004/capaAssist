"""evaluator.py — Evaluator Agent (Phase 4).

Entry point: run(agent_input, repo) -> (EvaluationResult, RecurrenceResult)

3 layers:
  Layer 1 (pure regex, no LLM) -> ownership, due_date_quality,
    evidence_requirement, effectiveness_check.
  Layer 2 Call A (LLM) -> clarity, specificity.
  Layer 2 Call B (LLM) -> action_theme + addresses_root_cause; Python derives
    root_cause_linkage / preventive_value / training_overreliance from it
    using config's taxonomy/category tables — the LLM never says `passed`
    for these 3 dimensions.
  Layer 3 recurrence -> filters ContextPackage.similar_capas (already
    semantic+structural merged by Phase 2) by root_cause_category, then (if
    any matches) compares the new action against full past-action text via
    an LLM call.

Call A, Call B, and recurrence run concurrently. Failures fail closed (no
silent pass). See phases/phase4.md.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import get_args

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

import config
from models.schemas import (
    ActionTheme,
    AgentInput,
    DimensionResult,
    EvaluationResult,
    RecurrenceResult,
)
from repositories.base import CapaRepository
from services.llm import call_llm_json

logger = logging.getLogger("capa_ai.evaluator")

_jinja_env = Environment(
    loader=FileSystemLoader(str(config.PROMPTS_DIR)), trim_blocks=True, lstrip_blocks=True
)

_ACTION_THEMES: list[str] = list(get_args(ActionTheme))

# --- Layer 1: rule-based gap detection (no LLM) -----------------------------
# Tightened to require a specific role/assignment signal, not a bare
# department/team name.
_RE_OWNERSHIP = re.compile(
    r"\b(assign(ed)?\s+to|named\s+owner|owner\s*:|responsible\s+(party|person|role)?|"
    r"accountable|led\s+by|managed\s+by|overseen\s+by|"
    r"supervisor|manager|officer|engineer|technician|inspector|coordinator)\b",
    re.IGNORECASE,
)
# Requires an actual date/number, not "immediately"/"asap" with no concrete timeline.
_RE_DUE_DATE = re.compile(
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d+\s+(days?|weeks?|months?)|"
    r"\b(by|before|within|no\s+later\s+than)\b\s*\w*\s*\d)",
    re.IGNORECASE,
)
# Requires a specific evidence artifact, not a bare "report"/"record"/"document".
_RE_EVIDENCE = re.compile(
    r"\b(evidence|documentation|checklist|photo|photograph|sign-?off|certificate|"
    r"audit\s+trail|test\s+result|inspection\s+report|incident\s+report|"
    r"completed\s+form|signed\s+(record|log|report|document)|"
    r"documented\s+(record|proof))\b",
    re.IGNORECASE,
)
_RE_EFFECTIVENESS = re.compile(
    r"\b(effectiveness|effective|verify|verification|audit|re-?inspect|"
    r"follow-?up|review|monitor|KPI|metric|re-?assess|validate|confirm|"
    r"measure|track|post-?completion|performance\s+check)\b",
    re.IGNORECASE,
)


def _rule_based(action_text: str) -> dict[str, DimensionResult]:
    """Layer 1: keyword scan for the 4 structurally detectable dimensions."""

    def _check(pattern: re.Pattern, ok: str, fail: str) -> DimensionResult:
        passed = bool(pattern.search(action_text))
        return DimensionResult(passed=passed, reason=ok if passed else fail)

    return {
        "ownership": _check(
            _RE_OWNERSHIP,
            "A responsible role or person is mentioned.",
            "No responsible owner or role is mentioned.",
        ),
        "due_date_quality": _check(
            _RE_DUE_DATE,
            "A concrete timeline or due date is present.",
            "No concrete due date or timeline is specified.",
        ),
        "evidence_requirement": _check(
            _RE_EVIDENCE,
            "A specific evidence/documentation artifact is stated.",
            "No specific evidence or documentation requirement is specified.",
        ),
        "effectiveness_check": _check(
            _RE_EFFECTIVENESS,
            "An effectiveness verification method is described.",
            "No post-completion verification method is described.",
        ),
    }


# --- Layer 2: LLM calls ------------------------------------------------------


class _CallAResult(BaseModel):
    clarity: DimensionResult
    specificity: DimensionResult


class _CallBResult(BaseModel):
    action_theme: ActionTheme
    addresses_root_cause: bool
    addresses_root_cause_reason: str


async def _call_a(action_text: str, agent_input: AgentInput) -> _CallAResult:
    ctx = agent_input.context_package
    template = _jinja_env.get_template("evaluator/structural.jinja2")
    prompt = template.render(
        org_name=config.ORG_NAME,
        action_text=action_text,
        problem_summary=ctx.problem_summary,
        severity=ctx.severity,
        site_id=ctx.site_id,
    )
    return await call_llm_json(
        [{"role": "user", "content": prompt}],
        model=config.PRIMARY_MODEL,
        schema_class=_CallAResult,
        temperature=0.1,
    )


async def _call_b(action_text: str, agent_input: AgentInput) -> _CallBResult:
    ctx = agent_input.context_package
    template = _jinja_env.get_template("evaluator/classify.jinja2")
    prompt = template.render(
        org_name=config.ORG_NAME,
        action_text=action_text,
        problem_summary=ctx.problem_summary,
        root_cause=ctx.root_cause,
        root_cause_category=ctx.root_cause_category,
        contributing_factors=agent_input.capa_input.contributing_factors,
        missing_controls=agent_input.capa_input.missing_controls,
        similar_capas=ctx.similar_capas[:5],
        action_themes=_ACTION_THEMES,
    )
    return await call_llm_json(
        [{"role": "user", "content": prompt}],
        model=config.PRIMARY_MODEL,
        schema_class=_CallBResult,
        temperature=0.1,
    )


def _derive_from_classification(
    classification: _CallBResult, root_cause_category: str | None
) -> dict[str, DimensionResult]:
    """Python-only derivation of root_cause_linkage / preventive_value /
    training_overreliance from Call B's classification + config's taxonomy
    tables. The LLM never asserts `passed` for any of these three —
    see phases/phase4.md decision 2."""
    theme = classification.action_theme
    category = root_cause_category

    compatible_themes = config.ROOT_CAUSE_CATEGORY_THEME_MAP.get(category, set())
    theme_compatible = theme in compatible_themes
    linkage_passed = classification.addresses_root_cause and theme_compatible
    if linkage_passed:
        linkage_reason = (
            f"Action's control theme ({theme}) is compatible with root-cause category "
            f"{category!r} and {classification.addresses_root_cause_reason.lower()}"
        )
    elif not theme_compatible:
        linkage_reason = (
            f"Action's control theme ({theme}) is not a structurally compatible response "
            f"to root-cause category {category!r}."
        )
    else:
        linkage_reason = classification.addresses_root_cause_reason

    strength = config.CONTROL_STRENGTH_RUBRIC.get(theme, 0)
    preventive_passed = strength >= config.PREVENTIVE_VALUE_PASS_THRESHOLD
    preventive_reason = (
        f"{theme} control strength ({strength}) "
        f"{'meets' if preventive_passed else 'is below'} the pass threshold "
        f"({config.PREVENTIVE_VALUE_PASS_THRESHOLD})."
    )

    training_sufficient = category in config.TRAINING_SUFFICIENT_CATEGORIES
    overreliance_passed = theme != "Training" or training_sufficient
    overreliance_reason = (
        f"Action's primary control is {theme}, not training-only."
        if theme != "Training"
        else (
            f"Training is a sufficient systemic fix for root-cause category {category!r}."
            if training_sufficient
            else f"Action relies solely on training for root-cause category {category!r}, "
            "which needs a more systemic control."
        )
    )

    return {
        "root_cause_linkage": DimensionResult(passed=linkage_passed, reason=linkage_reason),
        "preventive_value": DimensionResult(passed=preventive_passed, reason=preventive_reason),
        "training_overreliance": DimensionResult(
            passed=overreliance_passed, reason=overreliance_reason
        ),
    }


_FAIL_CLOSED_CALL_A = {
    "clarity": DimensionResult(passed=False, reason="Structural evaluation failed — failing closed."),
    "specificity": DimensionResult(
        passed=False, reason="Structural evaluation failed — failing closed."
    ),
}
_FAIL_CLOSED_CALL_B = {
    "root_cause_linkage": DimensionResult(
        passed=False, reason="Root-cause classification failed — failing closed."
    ),
    "preventive_value": DimensionResult(
        passed=False, reason="Root-cause classification failed — failing closed."
    ),
    "training_overreliance": DimensionResult(
        passed=False, reason="Root-cause classification failed — failing closed."
    ),
}


# --- Layer 3: recurrence -----------------------------------------------------


class _RecurrenceCompareResult(BaseModel):
    new_actions_are_same_as_past: bool
    past_actions_were_effective: bool | None = None
    recurrence_warning: str | None = None


async def _recurrence_check(
    action_text: str, agent_input: AgentInput, repo: CapaRepository
) -> RecurrenceResult:
    ctx = agent_input.context_package
    category = ctx.root_cause_category
    capa = agent_input.capa_input

    prior = [c for c in ctx.similar_capas if category and c.root_cause_category == category]
    prior_occurrence_count = len(prior)
    recurred_at_same_site = any(c.site_id == capa.site_id for c in prior) if capa.site_id else False

    if prior_occurrence_count == 0:
        return RecurrenceResult(recurrence_detected=False, prior_occurrence_count=0)

    capa_ids = [c.capa_id for c in prior]
    try:
        actions_by_capa = repo.fetch_actions_bulk(capa.tenant_id, capa_ids)
    except Exception as exc:
        logger.warning("fetch_actions_bulk failed for recurrence check: %s", exc)
        return RecurrenceResult(
            recurrence_detected=True,
            prior_occurrence_count=prior_occurrence_count,
            recurred_at_same_site=recurred_at_same_site,
            recurrence_warning=(
                f"This root-cause category has recurred {prior_occurrence_count} time(s) "
                "before, but past-action history could not be retrieved for comparison."
            ),
        )

    past_actions = [a for actions in actions_by_capa.values() for a in actions][:8]
    if not past_actions:
        return RecurrenceResult(
            recurrence_detected=True,
            prior_occurrence_count=prior_occurrence_count,
            recurred_at_same_site=recurred_at_same_site,
            recurrence_warning=(
                f"This root-cause category has recurred {prior_occurrence_count} time(s) "
                "before, but no past action records were found to compare against."
            ),
        )

    template = _jinja_env.get_template("evaluator/recurrence.jinja2")
    prompt = template.render(
        org_name=config.ORG_NAME,
        action_text=action_text,
        prior_occurrence_count=prior_occurrence_count,
        past_actions=past_actions,
    )
    comparison = await call_llm_json(
        [{"role": "user", "content": prompt}],
        model=config.PRIMARY_MODEL,
        schema_class=_RecurrenceCompareResult,
        temperature=0.1,
    )
    return RecurrenceResult(
        recurrence_detected=True,
        prior_occurrence_count=prior_occurrence_count,
        recurred_at_same_site=recurred_at_same_site,
        past_actions_were_effective=comparison.past_actions_were_effective,
        new_actions_are_same_as_past=comparison.new_actions_are_same_as_past,
        recurrence_warning=comparison.recurrence_warning,
    )


# --- Entry point --------------------------------------------------------------


async def run(
    agent_input: AgentInput, repo: CapaRepository
) -> tuple[EvaluationResult, RecurrenceResult]:
    if not agent_input.action_text:
        raise ValueError("agent_input.action_text is required for the Evaluator")

    action_text = agent_input.action_text
    layer1 = _rule_based(action_text)

    call_a_result, call_b_result, recurrence = await asyncio.gather(
        _call_a(action_text, agent_input),
        _call_b(action_text, agent_input),
        _recurrence_check(action_text, agent_input, repo),
        return_exceptions=True,
    )

    if isinstance(call_a_result, Exception):
        logger.warning("Call A failed: %s. Using fail-closed defaults.", call_a_result)
        call_a_dims = _FAIL_CLOSED_CALL_A
    else:
        call_a_dims = {"clarity": call_a_result.clarity, "specificity": call_a_result.specificity}

    if isinstance(call_b_result, Exception):
        logger.warning("Call B failed: %s. Using fail-closed defaults.", call_b_result)
        call_b_dims = _FAIL_CLOSED_CALL_B
    else:
        call_b_dims = _derive_from_classification(
            call_b_result, agent_input.context_package.root_cause_category
        )

    if isinstance(recurrence, Exception):
        logger.warning("Recurrence check failed: %s. Treating as no recurrence detected.", recurrence)
        recurrence = RecurrenceResult(recurrence_detected=False, prior_occurrence_count=0)

    evaluation = EvaluationResult(**layer1, **call_a_dims, **call_b_dims)
    return evaluation, recurrence
