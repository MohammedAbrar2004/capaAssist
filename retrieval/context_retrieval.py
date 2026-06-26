"""Context Retrieval Agent — the most important agent in the system (every
downstream agent's output quality is bounded by this one). Runs first,
always: normalize -> enrich -> retrieve (selective, per RETRIEVAL_CONFIG) ->
assembled, deduplicated, schema-valid ContextPackage. See phases/phase2.md.
"""

import asyncio

import config
from models.schemas import (
    CAPARecord,
    ContextPackage,
    EffectiveActionSummary,
    NL2SQLResult,
    SimilarCapaSummary,
    SopExcerpt,
    RegulatoryExcerpt,
)
from repositories.base import CapaRepository
from retrieval import nl2sql, sql_retrieval, vector_retrieval
from retrieval.enrich import enrich
from retrieval.normalize import normalize


async def get_context_package(
    capa_input: CAPARecord, agent_name: str, repo: CapaRepository
) -> ContextPackage:
    normalized, missing_fields = normalize(capa_input)
    inferred = await enrich(normalized, missing_fields)

    effective_severity = (
        inferred["severity"].value if "severity" in inferred else normalized.get("severity")
    )
    tenant_id: str = normalized["tenant_id"]
    site_id = normalized.get("site_id")
    category_id = normalized.get("root_cause_category")
    query_text = normalized.get("root_cause_statement") or normalized["description"]

    systems = config.RETRIEVAL_CONFIG.get(agent_name, [])

    tasks: dict[str, asyncio.Future] = {}
    if "sql" in systems:
        tasks["sql_similar"] = asyncio.to_thread(
            sql_retrieval.fetch_similar_capas, repo, tenant_id, site_id, category_id
        )
        tasks["sql_effective"] = asyncio.to_thread(
            sql_retrieval.fetch_effective_actions, repo, tenant_id
        )
    if "vector" in systems:
        tasks["vector_similar"] = asyncio.to_thread(
            vector_retrieval.search_historical_capas, query_text
        )
    if "sop" in systems:
        tasks["sops"] = asyncio.to_thread(vector_retrieval.search_sops, query_text)
    if "regulatory" in systems:
        tasks["regulatory"] = asyncio.to_thread(vector_retrieval.search_regulatory, query_text)
    if "nl2sql" in systems and site_id:
        question = nl2sql.build_employee_question(site_id, category_id)
        tasks["nl2sql"] = nl2sql.run_nl2sql(question, tenant_id)

    results = dict(zip(tasks.keys(), await asyncio.gather(*tasks.values()))) if tasks else {}

    similar_is_fallback = False
    by_capa_id: dict[str, SimilarCapaSummary] = {}
    if "sql_similar" in results:
        sql_similar, similar_is_fallback = results["sql_similar"]
        for c in sql_similar:
            by_capa_id[c.capa_id] = c

    if "vector_similar" in results:
        # Merge by capa_id — on a collision, keep whichever side scored
        # higher (structural matches score 1.0, fallback scores 0.1, so a
        # real vector hit can outrank fallback "recent CAPAs" junk here).
        for v in results["vector_similar"]:
            if not v.capa_id:
                continue
            existing = by_capa_id.get(v.capa_id)
            if existing is None or (v.similarity_score or 0) > (existing.similarity_score or 0):
                by_capa_id[v.capa_id] = v

    # Sub-Phase 2b: rank by similarity_score (unified relevance ordering,
    # not insertion order) then cap the list size.
    similar_capas = sorted(
        by_capa_id.values(), key=lambda c: c.similarity_score or 0.0, reverse=True
    )[: config.MAX_SIMILAR_CAPAS]

    effective_actions: list[EffectiveActionSummary] = results.get("sql_effective", [])
    relevant_sops: list[SopExcerpt] = results.get("sops", [])
    regulatory_context: list[RegulatoryExcerpt] = results.get("regulatory", [])
    enterprise_context: list[NL2SQLResult] = [results["nl2sql"]] if "nl2sql" in results else []

    return ContextPackage(
        problem_summary=normalized["description"],
        root_cause=normalized.get("root_cause_statement"),
        root_cause_category=category_id,
        severity=effective_severity,
        site_id=site_id,
        owner_group_id=normalized.get("owner_group_id"),
        similar_capas=similar_capas,
        similar_capas_is_fallback=similar_is_fallback,
        effective_actions=effective_actions,
        relevant_sops=relevant_sops,
        regulatory_context=regulatory_context,
        missing_fields=missing_fields,
        inferred_fields=inferred,
        enterprise_context=enterprise_context,
    )
