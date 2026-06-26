"""generator.py — Generator Agent (Phase 3, Sub-Phase 3b 2-call redesign).

Entry point: run(agent_input, repo) -> list[GeneratedAction]

Two LLM calls instead of one (see phases/phase3.md Sub-Phase 3b decision 1):
  1. skeleton.jinja2 — decides WHAT the action is (type/title/requirements/
     linked_root_cause/rationale), from the CAPA's own fields + themes +
     existing-actions context only.
  2. enrich.jinja2   — adds the operational details (owner role/due date/
     evidence/effectiveness check/confidence/similar_capa_reference) using
     the heavy historical/SOP/regulatory/enterprise context.
Each call validates + retries once independently, then the two halves merge
by index into GeneratedAction. See phases/phase3.md.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Callable

from jinja2 import Environment, FileSystemLoader
from pydantic import ValidationError

import config
from models.schemas import ActionEnrichment, ActionSkeleton, AgentInput, GeneratedAction
from repositories.base import CapaRepository
from services.llm import TruncatedResponseError, call_llm, strip_fences

logger = logging.getLogger("capa_ai.generator")

_jinja_env = Environment(
    loader=FileSystemLoader(str(config.PROMPTS_DIR)), trim_blocks=True, lstrip_blocks=True
)


def _render_skeleton_prompt(agent_input: AgentInput, num_actions: int, repo: CapaRepository) -> str:
    ctx = agent_input.context_package
    action_type = agent_input.action_type
    try:
        action_themes = repo.fetch_action_taxonomy(action_type)
    except Exception as exc:
        logger.warning("Failed to load action_taxonomy for %s: %s", action_type, exc)
        action_themes = []
    template = _jinja_env.get_template("generator/skeleton.jinja2")
    return template.render(
        org_name=config.ORG_NAME,
        action_type=action_type,
        num_actions=num_actions,
        problem_summary=ctx.problem_summary,
        root_cause=ctx.root_cause,
        root_cause_category=ctx.root_cause_category,
        severity=ctx.severity,
        site_id=ctx.site_id,
        owner_group_id=ctx.owner_group_id,
        missing_controls=agent_input.capa_input.missing_controls,
        action_themes=action_themes,
        existing_actions=agent_input.capa_input.existing_actions,
    )


def _render_enrich_prompt(
    agent_input: AgentInput, skeletons: list[ActionSkeleton], num_actions: int
) -> str:
    ctx = agent_input.context_package
    template = _jinja_env.get_template("generator/enrich.jinja2")
    skeleton_json = json.dumps([s.model_dump(mode="json") for s in skeletons], indent=2)
    return template.render(
        org_name=config.ORG_NAME,
        action_type=agent_input.action_type,
        num_actions=num_actions,
        skeleton_json=skeleton_json,
        similar_capas=ctx.similar_capas[:5],
        effective_actions=ctx.effective_actions[:5],
        relevant_sops=ctx.relevant_sops,
        regulatory_context=ctx.regulatory_context,
        enterprise_context=ctx.enterprise_context,
        due_date_windows=config.DUE_DATE_WINDOWS,
        today=date.today().isoformat(),
    )


def _validate_due_date_windows(actions: list[GeneratedAction]) -> None:
    """Raise ValueError if any action's due date falls outside its type's expected window."""
    today = date.today()
    violations: list[str] = []
    for action in actions:
        window = config.DUE_DATE_WINDOWS.get(action.type)
        if not window:
            continue
        days_out = (action.recommended_due_date - today).days
        lo, hi = window
        if not (lo <= days_out <= hi):
            violations.append(
                f"{action.type} action's due date ({action.recommended_due_date}, {days_out} days out) "
                f"is outside the expected {lo}-{hi} day window for this action type."
            )
    if violations:
        raise ValueError("Due date window violation(s): " + " | ".join(violations))


def _parse_skeletons(raw: str, action_type: str) -> list[ActionSkeleton]:
    text = strip_fences(raw)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")

    skeletons: list[ActionSkeleton] = []
    for item in data:
        returned_type = item.get("type")
        if returned_type and returned_type != action_type:
            logger.warning(
                "Generator skeleton returned type=%r for a requested type=%r action — overwriting.",
                returned_type, action_type,
            )
        item["type"] = action_type
        skeletons.append(ActionSkeleton.model_validate(item))
    return skeletons


def _parse_enrichments(raw: str, expected_len: int) -> list[ActionEnrichment]:
    text = strip_fences(raw)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")
    if len(data) != expected_len:
        raise ValueError(
            f"Expected {expected_len} enrichment object(s) (one per action, same order), got {len(data)}"
        )
    return [ActionEnrichment.model_validate(item) for item in data]


async def _call_with_retry(
    render_messages_fn: Callable[[], list[dict]],
    parse_fn: Callable[[str], list],
    max_tokens: int,
    correction_fn: Callable[[Exception], str],
) -> tuple[list, str]:
    """Shared retry-once-then-raise loop for both the skeleton and enrich
    calls. render_messages_fn() builds the initial messages (called once);
    on a retry, a correction turn from correction_fn(exc) is appended
    instead of re-rendering from scratch. parse_fn(raw) -> parsed list,
    raising on failure."""
    messages = render_messages_fn()
    last_exc: Exception | None = None
    raw = ""
    for attempt in range(2):
        try:
            raw = await call_llm(messages, model=config.PRIMARY_MODEL, temperature=0.4, max_tokens=max_tokens)
            parsed = parse_fn(raw)
            return parsed, raw
        except TruncatedResponseError as exc:
            last_exc = exc
            raw = exc.content
            if attempt == 0:
                max_tokens = int(max_tokens * 1.5)
                correction = (
                    "Your previous response was cut off before the JSON array finished "
                    "(ran out of output budget). Return ONLY the complete, valid JSON array — "
                    "keep text concise so it fits."
                )
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": correction},
                ]
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_exc = exc
            if attempt == 0:
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": correction_fn(exc)},
                ]
    raise ValueError(f"Generator failed after 2 attempts: {last_exc}")


def _skeleton_correction(num_actions: int) -> Callable[[Exception], str]:
    def _correction(exc: Exception) -> str:
        if isinstance(exc, json.JSONDecodeError):
            return (
                f"Your response was not valid JSON: {exc}\n"
                f"Return ONLY a valid JSON array of {num_actions} action object(s). No markdown, no explanation."
            )
        if isinstance(exc, ValidationError):
            if "mandatory" in str(exc) or "requirements" in str(exc):
                return (
                    f"Your JSON failed requirements validation: {exc}\n"
                    "Remember: every action needs >=1 requirement. A requirement with "
                    "\"mandatory\": true must have EXACTLY 1 option. A requirement with "
                    "\"mandatory\": false must have 2 to 5 meaningfully different options. "
                    f"Return ONLY a corrected JSON array of {num_actions} action object(s)."
                )
            if "rationale" in str(exc):
                return (
                    f"Your JSON failed validation: {exc}\n"
                    "rationale must be 1-2 concise sentences, not a paragraph. "
                    f"Return ONLY a corrected JSON array of {num_actions} action object(s)."
                )
            return (
                f"Your JSON was syntactically valid but failed schema validation: {exc}\n"
                "Check field names and types match the required schema exactly, then "
                f"return ONLY a corrected JSON array of {num_actions} action object(s)."
            )
        return (
            f"Your response failed validation: {exc}\n"
            f"Return ONLY a valid JSON array of {num_actions} action object(s). No markdown, no explanation."
        )
    return _correction


def _enrich_correction(num_actions: int) -> Callable[[Exception], str]:
    def _correction(exc: Exception) -> str:
        if isinstance(exc, json.JSONDecodeError):
            return (
                f"Your response was not valid JSON: {exc}\n"
                f"Return ONLY a valid JSON array of {num_actions} object(s). No markdown, no explanation."
            )
        if isinstance(exc, ValueError) and "Expected" in str(exc) and "enrichment" in str(exc):
            return (
                f"{exc}\n"
                f"Return exactly {num_actions} object(s) in a JSON array, same order as the input actions."
            )
        if isinstance(exc, ValidationError) and "required_evidence" in str(exc):
            return (
                f"Your JSON failed validation: {exc}\n"
                "required_evidence must have at least 2 items. "
                f"Return ONLY a corrected JSON array of {num_actions} object(s)."
            )
        return (
            f"Your response failed validation: {exc}\n"
            f"Return ONLY a valid JSON array of {num_actions} object(s), same order as the input actions."
        )
    return _correction


async def run(
    agent_input: AgentInput, repo: CapaRepository, num_actions: int = 2
) -> list[GeneratedAction]:
    """Generate 1-3 CAPA actions of the requested type, via a skeleton call
    followed by an enrich call (see module docstring).

    Parameters
    ----------
    agent_input : AgentInput with CAPARecord + ContextPackage + action_type
    repo        : CapaRepository — used to fetch action_taxonomy themes
    num_actions : how many action variants to produce (default 2, max 3)
    """
    if not agent_input.action_type:
        raise ValueError("agent_input.action_type is required for the Generator")

    num_actions = max(1, min(3, num_actions))
    action_type = agent_input.action_type

    skeleton_max_tokens = 800 + 400 * num_actions
    skeletons, _ = await _call_with_retry(
        render_messages_fn=lambda: [
            {"role": "user", "content": _render_skeleton_prompt(agent_input, num_actions, repo)}
        ],
        parse_fn=lambda raw: _parse_skeletons(raw, action_type),
        max_tokens=skeleton_max_tokens,
        correction_fn=_skeleton_correction(num_actions),
    )

    enrich_max_tokens = 1000 + 500 * num_actions
    enrichments, _ = await _call_with_retry(
        render_messages_fn=lambda: [
            {"role": "user", "content": _render_enrich_prompt(agent_input, skeletons, num_actions)}
        ],
        parse_fn=lambda raw: _parse_enrichments(raw, len(skeletons)),
        max_tokens=enrich_max_tokens,
        correction_fn=_enrich_correction(num_actions),
    )

    merged = [
        GeneratedAction.model_validate({**sk.model_dump(), **en.model_dump()})
        for sk, en in zip(skeletons, enrichments)
    ]
    _validate_due_date_windows(merged)
    return merged
