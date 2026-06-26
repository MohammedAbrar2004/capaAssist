"""Pipeline sequencing for every AI endpoint: resolve context -> call agent
-> score -> cache/persist -> audit. Lifted out of api/routes.py in Phase 7 so
that module can stay genuinely routing-only (parse request, call a
dispatch.run_* function, shape the response). See phases/phase7.md decision 1.
"""

import uuid

from fastapi import HTTPException

import config
from agents import evaluator, explainability, generator, improver
from engines import scoring_engine
from models.schemas import (
    AgentInput,
    AuditTrailEntry,
    CAPARecord,
    EvaluateActionResponse,
    Evaluation,
    ExplainActionResponse,
    GenerateActionsResponse,
    ImproveActionResponse,
)
from repositories.base import CapaRepository
from retrieval.context_retrieval import get_context_package
from services import eval_cache


def _resolve_action_text(capa: CAPARecord, repo: CapaRepository) -> str:
    """Shared by evaluate/improve/explain: resolve flat action text from
    capa.action_id (existing CAPA_ACTIONS row) or capa.actions[0] (ad-hoc
    free text). See phases/phase4.md decision 1."""
    if capa.action_id:
        existing_actions = repo.fetch_actions(capa.tenant_id, capa.capa_id)
        match = next((a for a in existing_actions if a.action_id == capa.action_id), None)
        if not match:
            raise HTTPException(
                status_code=404, detail=f"action_id {capa.action_id!r} not found on this CAPA"
            )
        return f"{match.action_title}: {match.action_description}"
    if capa.actions:
        return capa.actions[0]
    raise HTTPException(status_code=422, detail="Either action_id or actions[0] is required")


async def _resolve_evaluation(
    capa: CAPARecord, agent_input: AgentInput, action_text: str, repo: CapaRepository
):
    """Shared by improve/explain: reuse a cached evaluation from a prior
    evaluate call in this process if present, otherwise evaluate fresh and
    populate the cache. See phases/phase5.md decisions 3-4."""
    cache_key = eval_cache.make_key(capa.tenant_id, capa.capa_id, capa.action_id, action_text)
    cached = eval_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        evaluation, recurrence = await evaluator.run(agent_input, repo)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    eval_cache.put(cache_key, (evaluation, recurrence))
    return evaluation, recurrence


async def run_generate(capa: CAPARecord, repo: CapaRepository) -> GenerateActionsResponse:
    if not capa.requested_action_type:
        raise HTTPException(status_code=422, detail="requested_action_type is required")

    context_package = await get_context_package(capa, "generator", repo)
    agent_input = AgentInput(
        capa_input=capa,
        context_package=context_package,
        action_type=capa.requested_action_type,
    )

    try:
        actions = await generator.run(agent_input, repo, num_actions=capa.num_actions or 2)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    request_id = str(uuid.uuid4())
    response = GenerateActionsResponse(
        request_id=request_id,
        capa_id=capa.capa_id,
        action_type=capa.requested_action_type,
        actions=actions,
        model_version=config.GENERATOR_MODEL_VERSION,
    )

    repo.write_audit(
        AuditTrailEntry(
            request_id=request_id,
            tenant_id=capa.tenant_id,
            agent="generator",
            input_payload=capa.model_dump(mode="json"),
            output_payload=response.model_dump(mode="json"),
            model_version=config.GENERATOR_MODEL_VERSION,
        )
    )

    return response


async def run_evaluate(capa: CAPARecord, repo: CapaRepository) -> EvaluateActionResponse:
    """Score one CAPA action. Either capa.action_id (an existing
    CAPA_ACTIONS row - result is persisted) or capa.actions[0] (ad-hoc free
    text - scored but not persisted, no FK target). See phases/phase4.md
    decision 1."""
    action_text = _resolve_action_text(capa, repo)

    context_package = await get_context_package(capa, "evaluator", repo)
    agent_input = AgentInput(
        capa_input=capa, context_package=context_package, action_text=action_text
    )

    try:
        evaluation, recurrence = await evaluator.run(agent_input, repo)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    scoring = scoring_engine.compute_score(evaluation, recurrence)

    eval_cache.put(
        eval_cache.make_key(capa.tenant_id, capa.capa_id, capa.action_id, action_text),
        (evaluation, recurrence),
    )

    request_id = str(uuid.uuid4())
    response = EvaluateActionResponse(
        request_id=request_id,
        capa_id=capa.capa_id,
        action_id=capa.action_id,
        score=scoring.score,
        weakness_level=scoring.weakness_level,
        evaluation=evaluation,
        recurrence=scoring.recurrence,
        failed_dimensions=scoring.failed_dimensions,
        model_version=config.EVALUATOR_MODEL_VERSION,
    )

    if capa.action_id:
        repo.write_evaluation(
            Evaluation(
                eval_id=str(uuid.uuid4()),
                action_id=capa.action_id,
                tenant_id=capa.tenant_id,
                score=float(scoring.score),
                weakness_level=scoring.weakness_level,
                dimension_results=evaluation.model_dump(mode="json"),
                model_version=config.EVALUATOR_MODEL_VERSION,
            )
        )

    repo.write_audit(
        AuditTrailEntry(
            request_id=request_id,
            tenant_id=capa.tenant_id,
            agent="evaluator",
            input_payload=capa.model_dump(mode="json"),
            output_payload=response.model_dump(mode="json"),
            model_version=config.EVALUATOR_MODEL_VERSION,
        )
    )

    return response


async def run_improve(capa: CAPARecord, repo: CapaRepository) -> ImproveActionResponse:
    """Rewrite one weak CAPA action. Reuses a cached evaluation from a prior
    evaluate call in this process if present; otherwise evaluates fresh.
    Never persists the improved text (human-in-the-loop) - only writes an
    audit-trail entry. See phases/phase5.md decisions 3-4 and 7."""
    action_text = _resolve_action_text(capa, repo)

    context_package = await get_context_package(capa, "improver", repo)
    agent_input = AgentInput(
        capa_input=capa, context_package=context_package, action_text=action_text
    )

    evaluation, recurrence = await _resolve_evaluation(capa, agent_input, action_text, repo)

    try:
        result = await improver.run(agent_input, evaluation, recurrence)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    request_id = str(uuid.uuid4())
    response = ImproveActionResponse(
        request_id=request_id,
        capa_id=capa.capa_id,
        action_id=capa.action_id,
        original_action_text=result.original_action_text,
        improved_action_title=result.improved_action_title,
        improved_action_description=result.improved_action_description,
        changes_explained=result.changes_explained,
        additional_actions=result.additional_actions,
        model_version=config.IMPROVER_MODEL_VERSION,
    )

    repo.write_audit(
        AuditTrailEntry(
            request_id=request_id,
            tenant_id=capa.tenant_id,
            agent="improver",
            input_payload=capa.model_dump(mode="json"),
            output_payload=response.model_dump(mode="json"),
            model_version=config.IMPROVER_MODEL_VERSION,
        )
    )

    return response


async def run_explain(capa: CAPARecord, repo: CapaRepository) -> ExplainActionResponse:
    """Plain-language explanation of an evaluation. Reuses a cached
    evaluation from a prior evaluate call in this process if present;
    otherwise evaluates fresh (using the evaluator's own retrieval config,
    since that's what a cache-miss fresh evaluation needs). The
    Explainability agent itself never raises - only the eval-resolution step
    can 502. See phases/phase6.md decisions 1-2 and 4."""
    action_text = _resolve_action_text(capa, repo)

    context_package = await get_context_package(capa, "evaluator", repo)
    agent_input = AgentInput(
        capa_input=capa, context_package=context_package, action_text=action_text
    )

    evaluation, recurrence = await _resolve_evaluation(capa, agent_input, action_text, repo)
    scoring = scoring_engine.compute_score(evaluation, recurrence)

    explanation = await explainability.run(evaluation, scoring, action_text)

    request_id = str(uuid.uuid4())
    response = ExplainActionResponse(
        request_id=request_id,
        capa_id=capa.capa_id,
        action_id=capa.action_id,
        explanation=explanation,
        score=scoring.score,
        weakness_level=scoring.weakness_level,
        model_version=config.EXPLAINABILITY_MODEL_VERSION,
    )

    repo.write_audit(
        AuditTrailEntry(
            request_id=request_id,
            tenant_id=capa.tenant_id,
            agent="explainability",
            input_payload=capa.model_dump(mode="json"),
            output_payload=response.model_dump(mode="json"),
            model_version=config.EXPLAINABILITY_MODEL_VERSION,
        )
    )

    return response
