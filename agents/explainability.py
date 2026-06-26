"""explainability.py — Explainability Agent (Phase 6).

Entry point: run(eval_result, scoring_result, action_text) -> str

No context retrieval (config.RETRIEVAL_CONFIG["explainability"] = []).
Works only from the EvaluationResult + ScoringResult passed in by the route
(cached from a prior /capa/evaluate call, or freshly evaluated on a cache
miss — same resolution /capa/improve already does). Uses LIGHT_MODEL.
Returns plain prose, never JSON.

Non-blocking by design: unlike every other agent in this build, a failure
here never raises — it returns a deterministic fallback string instead. See
phases/phase6.md decision 4.
"""

from __future__ import annotations

import logging

from jinja2 import Environment, FileSystemLoader

import config
from models.schemas import ALL_DIMENSIONS, EvaluationResult, ScoringResult
from services.llm import call_llm

logger = logging.getLogger("capa_ai.explainability")

_jinja_env = Environment(
    loader=FileSystemLoader(str(config.PROMPTS_DIR)), trim_blocks=True, lstrip_blocks=True
)


async def run(
    eval_result: EvaluationResult,
    scoring_result: ScoringResult,
    action_text: str,
) -> str:
    """Produce a plain-language explanation (<=120 words) of why an action
    scored the way it did. Returns a plain text string — no JSON, no
    markdown. Never raises: returns a fallback string on LLM failure."""
    dim_reasons = {dim: getattr(eval_result, dim).reason for dim in ALL_DIMENSIONS}

    recurrence_warning = (
        scoring_result.recurrence.recurrence_warning
        if scoring_result.recurrence.recurrence_detected
        else None
    )

    template = _jinja_env.get_template("explainability/explain.jinja2")
    prompt = template.render(
        org_name=config.ORG_NAME,
        action_text=action_text,
        score=scoring_result.score,
        weakness_level=scoring_result.weakness_level,
        failed_dimensions=scoring_result.failed_dimensions,
        dim_reasons=dim_reasons,
        recurrence_warning=recurrence_warning,
    )

    try:
        return await call_llm(
            [{"role": "user", "content": prompt}],
            model=config.LIGHT_MODEL,
            temperature=0.4,
        )
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        failed = ", ".join(scoring_result.failed_dimensions[:3]) or "several quality checks"
        return (
            f"This action scored {scoring_result.score}/100 "
            f"({scoring_result.weakness_level} weakness level). "
            f"It did not meet the required standard for: {failed}. "
            "A stronger action would name a specific owner, include a concrete deadline, "
            "require documented evidence, and directly address the stated root cause."
        )
