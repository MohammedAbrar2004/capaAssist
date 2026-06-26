"""SQL retrieval system — structured (non-semantic) similarity via the
repository layer. No raw SQL here; everything goes through CapaRepository.
Synchronous (psycopg2) — context_retrieval.py runs these via asyncio.to_thread
so they don't block the event loop alongside the async vector/LLM calls.

Sub-Phase 2b hardening (phases/phase2.md): bulk-fetches actions/RCA instead
of one query per candidate (was O(N) extra queries, now O(1) regardless of
N), and assigns a similarity_score so context_retrieval.py can rank these
against vector hits instead of just concatenating.
"""

from repositories.base import CapaRepository
from models.schemas import EffectiveActionSummary, SimilarCapaSummary

# Structural sql matches are authoritative when site/category actually
# filtered the result set — rank them at the top. The fallback path
# ("no site/category given, return N most recent CAPAs org-wide") is a
# last resort, not a real match — score it low so a genuinely relevant
# vector hit can outrank it once context_retrieval.py merges+sorts.
_STRUCTURAL_MATCH_SCORE = 1.0
_FALLBACK_MATCH_SCORE = 0.1


def fetch_similar_capas(
    repo: CapaRepository,
    tenant_id: str,
    site_id: str | None = None,
    category_id: str | None = None,
    limit: int = 10,
) -> tuple[list[SimilarCapaSummary], bool]:
    """Returns (summaries, is_fallback). is_fallback=True means no site/category
    filter could be applied (both None) — caller got the N most recent CAPAs
    org-wide, not a real structural match."""
    is_fallback = site_id is None and category_id is None
    capas = repo.fetch_similar_capas(tenant_id, site_id=site_id, category_id=category_id, limit=limit)

    capa_ids = [c.capa_id for c in capas]
    actions_by_capa = repo.fetch_actions_bulk(tenant_id, capa_ids)
    rca_by_capa = repo.fetch_rca_bulk(tenant_id, capa_ids)
    score = _FALLBACK_MATCH_SCORE if is_fallback else _STRUCTURAL_MATCH_SCORE

    summaries = []
    for capa in capas:
        actions = actions_by_capa.get(capa.capa_id, [])
        rca = rca_by_capa.get(capa.capa_id)
        capa_type = repo.fetch_capa_type(capa.capa_type_id)  # cached, not N+1
        first_action = actions[0] if actions else None
        summaries.append(
            SimilarCapaSummary(
                capa_id=capa.capa_id,
                title=capa.capa_title,
                root_cause_summary=(capa.root_cause or "")[:300],
                action_summary=first_action.action_title if first_action else "",
                action_type=capa_type.capa_type_name if capa_type else capa.capa_type_id,
                effectiveness_result=(
                    "Verified" if first_action and first_action.verified_date else "Pending"
                ) if first_action else None,
                site_id=capa.site_id,
                group_id=capa.owner_group_id,
                root_cause_category=rca.root_cause_category if rca else None,
                similarity_score=score,
            )
        )
    return summaries, is_fallback


def fetch_effective_actions(
    repo: CapaRepository, tenant_id: str, limit: int = 20
) -> list[EffectiveActionSummary]:
    """High-effectiveness historical actions (closed + verified) — the
    evidence base the Generator/Improver cite as 'similar CAPAs with this
    root cause had X% effectiveness historically'."""
    actions = repo.fetch_effective_actions(tenant_id)[:limit]
    capa_ids = list({a.capa_id for a in actions})
    capas_by_id = repo.fetch_capas_bulk(tenant_id, capa_ids)
    rca_by_capa = repo.fetch_rca_bulk(tenant_id, capa_ids)

    summaries = []
    for action in actions:
        capa = capas_by_id.get(action.capa_id)
        rca = rca_by_capa.get(action.capa_id)
        capa_type = repo.fetch_capa_type(action.capa_type_id)  # cached, not N+1
        summaries.append(
            EffectiveActionSummary(
                action_type=capa_type.capa_type_name if capa_type else action.capa_type_id,
                title=action.action_title,
                description=action.action_description,
                effectiveness_result="Verified",
                evidence_required=action.evidence_required,
                root_cause_category=rca.root_cause_category if rca else None,
                site_id=action.site_id,
                group_id=capa.owner_group_id if capa else None,
            )
        )
    return summaries


def count_recurrence(repo: CapaRepository, tenant_id: str, capa_id: str) -> int:
    return repo.count_recurrence(tenant_id, capa_id)
