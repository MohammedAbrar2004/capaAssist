"""Thin HTTP layer. Route handlers parse requests, call the orchestrator,
shape responses — no business logic lives here.

Per phases/phase3.md decision 3, AI endpoints shipped a minimal route
alongside each agent phase (3-6) instead of deferring all wiring to a single
Orchestrator/API phase. Phase 7 (phases/phase7.md) finished that job: the
pipeline-sequencing logic those routes had accreted now lives in
orchestrator/dispatch.py, and this module is genuinely routing-only — obtain
a repository, call the matching dispatch.run_*, return what it returns. The
3 GET routes added in Phase 7 are simple enough (one repository call, no
agent pipeline) that they don't need a dispatch function of their own.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

import config
from models.schemas import (
    AuditTrailListResponse,
    CAPARecord,
    CapaDetailResponse,
    CapaListResponse,
    ContextPackage,
    EvaluateActionResponse,
    ExplainActionResponse,
    GenerateActionsResponse,
    ImproveActionResponse,
)
from orchestrator import dispatch
from repositories.base import CapaRepository
from retrieval.context_retrieval import get_context_package
from services.db import get_repository

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/capa/context", response_model=ContextPackage)
async def get_context(capa: CAPARecord, agent_name: str = "generator") -> ContextPackage:
    """Phase 2 retrofit — exposes the Context Retrieval Agent directly for
    debugging/integration. Not an audited terminal AI decision, so no
    capa_ai_audit_trail write here (the agent that consumes this writes it)."""
    repo: CapaRepository = get_repository()
    return await get_context_package(capa, agent_name, repo)


@router.post("/capa/generate", response_model=GenerateActionsResponse)
async def generate_actions(capa: CAPARecord) -> GenerateActionsResponse:
    repo: CapaRepository = get_repository()
    return await dispatch.run_generate(capa, repo)


@router.post("/capa/evaluate", response_model=EvaluateActionResponse)
async def evaluate_action(capa: CAPARecord) -> EvaluateActionResponse:
    repo: CapaRepository = get_repository()
    return await dispatch.run_evaluate(capa, repo)


@router.post("/capa/improve", response_model=ImproveActionResponse)
async def improve_action(capa: CAPARecord) -> ImproveActionResponse:
    repo: CapaRepository = get_repository()
    return await dispatch.run_improve(capa, repo)


@router.post("/capa/explain", response_model=ExplainActionResponse)
async def explain_action(capa: CAPARecord) -> ExplainActionResponse:
    repo: CapaRepository = get_repository()
    return await dispatch.run_explain(capa, repo)


# --- Phase 7 — read endpoints. tenant_id is a required query param: no auth
# exists yet, so there's no session to infer a tenant from (never default to
# config.CAPA_TENANT_ID — that's a seed-time constant, not an auth boundary).
# See phases/phase7.md decision 4. -----------------------------------------


@router.get("/capa/{capa_id}", response_model=CapaDetailResponse)
def get_capa(capa_id: str, tenant_id: str) -> CapaDetailResponse:
    repo: CapaRepository = get_repository()
    capa = repo.fetch_capa(tenant_id, capa_id)
    if not capa:
        raise HTTPException(status_code=404, detail=f"capa_id {capa_id!r} not found")
    return CapaDetailResponse(
        capa=capa,
        actions=repo.fetch_actions(tenant_id, capa_id),
        rca=repo.fetch_rca(tenant_id, capa_id),
    )


@router.get("/capas", response_model=CapaListResponse)
def list_capas(
    tenant_id: str,
    site_id: Optional[str] = None,
    status_id: Optional[str] = None,
    limit: int = Query(default=config.DEFAULT_LIST_LIMIT, le=config.MAX_LIST_LIMIT, gt=0),
    offset: int = Query(default=0, ge=0),
) -> CapaListResponse:
    repo: CapaRepository = get_repository()
    items = repo.fetch_capas(tenant_id, limit, offset, site_id=site_id, status_id=status_id)
    total = repo.count_capas(tenant_id, site_id=site_id, status_id=status_id)
    return CapaListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/capa/{capa_id}/audit", response_model=AuditTrailListResponse)
def get_capa_audit_trail(
    capa_id: str,
    tenant_id: str,
    agent: Optional[str] = None,
    limit: int = Query(default=config.DEFAULT_LIST_LIMIT, le=config.MAX_LIST_LIMIT, gt=0),
    offset: int = Query(default=0, ge=0),
) -> AuditTrailListResponse:
    repo: CapaRepository = get_repository()
    items = repo.fetch_audit_trail(tenant_id, capa_id=capa_id, agent=agent, limit=limit, offset=offset)
    total = repo.count_audit_trail(tenant_id, capa_id=capa_id, agent=agent)
    return AuditTrailListResponse(items=items, total=total, limit=limit, offset=offset)
