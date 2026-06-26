"""improver.py — Improver Agent (Phase 5).

Entry point: run(agent_input, eval_result, recurrence) -> ImproverResult

Single LLM call rewriting the action so every failed dimension from
eval_result is resolved. Does not call the Evaluator itself — the caller
(api/routes.py) resolves eval_result/recurrence, either from
services.eval_cache or by running agents.evaluator fresh. See
phases/phase5.md decision 4.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import get_args

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

import config
from models.schemas import (
    ALL_DIMENSIONS,
    ActionType,
    AgentInput,
    EvaluationResult,
    GeneratedAction,
    ImproverResult,
    RecurrenceResult,
)
from services.llm import call_llm_json

_jinja_env = Environment(
    loader=FileSystemLoader(str(config.PROMPTS_DIR)), trim_blocks=True, lstrip_blocks=True
)

_ACTION_TYPES: list[str] = list(get_args(ActionType))

# Max additional actions proposed when the original can't structurally cover
# the root cause alone. See phases/phase5.md Sub-Phase 5b decision 1.
_MAX_ADDITIONAL_ACTIONS = 2


class _ImproverLLMResult(BaseModel):
    improved_action_title: str
    improved_action_description: str
    changes_explained: list[str]
    additional_actions: list[GeneratedAction] = []


async def run(
    agent_input: AgentInput,
    eval_result: EvaluationResult,
    recurrence: RecurrenceResult,
) -> ImproverResult:
    if not agent_input.action_text:
        raise ValueError("agent_input.action_text is required for the Improver")

    action_text = agent_input.action_text
    ctx = agent_input.context_package
    capa = agent_input.capa_input

    failed_gaps = [
        {"dimension": dim, "reason": getattr(eval_result, dim).reason}
        for dim in ALL_DIMENSIONS
        if not getattr(eval_result, dim).passed
    ]

    # Python decides WHETHER additional actions are needed (objective anchor,
    # same pattern as the Evaluator's Phase 4 decision 2): the original action
    # can't structurally cover the root cause alone when any of the 3
    # classification-derived dimensions failed. The LLM only generates
    # content for additional_actions when this is true — see
    # phases/phase5.md Sub-Phase 5b decision 1.
    needs_additional_actions = not (
        eval_result.root_cause_linkage.passed
        and eval_result.preventive_value.passed
        and eval_result.training_overreliance.passed
    )
    structural_gap_reasons = [
        getattr(eval_result, dim).reason
        for dim in ("root_cause_linkage", "preventive_value", "training_overreliance")
        if not getattr(eval_result, dim).passed
    ]

    template = _jinja_env.get_template("improver/rewrite.jinja2")
    prompt = template.render(
        org_name=config.ORG_NAME,
        original_action=action_text,
        failed_gaps=failed_gaps,
        edit_instruction=capa.edit_instruction,
        recurrence_warning=recurrence.recurrence_warning if recurrence else None,
        problem_summary=ctx.problem_summary,
        root_cause=ctx.root_cause,
        root_cause_category=ctx.root_cause_category,
        contributing_factors=capa.contributing_factors,
        missing_controls=capa.missing_controls,
        severity=ctx.severity,
        site_id=ctx.site_id,
        effective_actions=ctx.effective_actions[:5],
        relevant_sops=ctx.relevant_sops[:3],
        today=date.today().isoformat(),
        needs_additional_actions=needs_additional_actions,
        structural_gap_reasons=structural_gap_reasons,
        action_types=_ACTION_TYPES,
        due_date_windows=config.DUE_DATE_WINDOWS,
        max_additional_actions=_MAX_ADDITIONAL_ACTIONS,
    )

    result = await call_llm_json(
        [{"role": "user", "content": prompt}],
        model=config.PRIMARY_MODEL,
        schema_class=_ImproverLLMResult,
        temperature=0.3,
    )

    # Gate in Python, not the LLM: even if the model returns suggestions
    # unprompted, drop them unless the objective trigger fired.
    additional_actions = (
        result.additional_actions[:_MAX_ADDITIONAL_ACTIONS] if needs_additional_actions else []
    )

    return ImproverResult(
        original_action_text=action_text,
        improved_action_title=result.improved_action_title,
        improved_action_description=result.improved_action_description,
        changes_explained=[str(c) for c in result.changes_explained],
        additional_actions=additional_actions,
    )
