"""Checkpoint 2 — Context Retrieval Agent.

10 varied CAPARecord inputs against the live seeded capa_assist DB + ChromaDB
+ live LLM (Groq). Self-skips (via the `repo` fixture) if the dev DB is
unreachable. Asserts structural properties from phases/phase2.md's
checkpoint, not exact LLM wording (an LLM-graded field can vary run to run).
"""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import config  # noqa: E402
from models.schemas import CAPARecord, ContextPackage  # noqa: E402
from retrieval.context_retrieval import get_context_package  # noqa: E402


def _capa(**overrides) -> CAPARecord:
    base = dict(
        tenant_id="TENANT_ACERTECH",
        capa_id="CAPA_CHECKPOINT2_TEST",
        title="Wire rope fraying on overhead crane",
        description="Inspection found frayed wire rope strands on overhead crane OC-001.",
        source_module="Inspection",
        site_id="SITE_01",
        severity="High",
        capa_type="Corrective",
        root_cause_category="CAT_EQUIPMENT_FAULT",
        root_cause_statement="Wire rope inspection criteria not specified per ISO 4309.",
    )
    base.update(overrides)
    return CAPARecord(**base)


CASES = [
    ("complete_generator", _capa(), "generator"),
    ("complete_evaluator", _capa(), "evaluator"),
    ("complete_improver", _capa(), "improver"),
    ("missing_severity", _capa(severity=None), "generator"),
    ("missing_owner_group", _capa(owner_group_id=None), "generator"),
    ("incident_source", _capa(source_module="Incident", title="LTI on warehouse floor",
                               description="A warehouse associate sustained a fracture after being struck by a forklift."),
     "generator"),
    ("audit_source", _capa(source_module="Audit", title="ISO 45001 audit finding",
                            description="Audit finding: PPE compliance records incomplete at Site 3.",
                            site_id="SITE_03"),
     "evaluator"),
    ("no_site_no_category", _capa(site_id=None, root_cause_category=None), "generator"),
    ("minimal_input", CAPARecord(
        tenant_id="TENANT_ACERTECH", capa_id="CAPA_CHECKPOINT2_MINIMAL",
        title="Spill in chemical storage", description="Minor chemical spill reported in bay 3.",
        source_module="Near Miss",
    ), "generator"),
    ("explainability_no_retrieval", _capa(), "explainability"),
]


@pytest.mark.parametrize("name,capa_input,agent_name", CASES, ids=[c[0] for c in CASES])
@pytest.mark.asyncio
async def test_context_package_checkpoint(name, capa_input, agent_name, repo):
    pkg = await get_context_package(capa_input, agent_name, repo)

    assert isinstance(pkg, ContextPackage)  # validates by construction
    assert pkg.problem_summary

    if agent_name == "explainability":
        assert pkg.similar_capas == []
        assert pkg.effective_actions == []
        assert pkg.relevant_sops == []
        assert pkg.regulatory_context == []
        assert pkg.enterprise_context == []
        return

    # missing_fields correctness: every field we set to None on the input
    # (and didn't get enriched) must show up.
    for field in ("site_id", "owner_group_id", "severity", "priority", "due_date",
                  "capa_type", "root_cause_statement", "root_cause_category"):
        raw_value = getattr(capa_input, field)
        if raw_value is None and field not in pkg.inferred_fields:
            assert field in pkg.missing_fields

    # similar_capas deduplicated by capa_id
    ids = [c.capa_id for c in pkg.similar_capas]
    assert len(ids) == len(set(ids))

    # inferred fields always tagged with confidence
    for inferred in pkg.inferred_fields.values():
        assert inferred.source == "inferred"
        assert 0.0 <= inferred.confidence <= 1.0

    # at least one result per configured system when data exists for it
    if "sql" in config.RETRIEVAL_CONFIG[agent_name]:
        assert len(pkg.effective_actions) > 0
    if "sop" in config.RETRIEVAL_CONFIG[agent_name]:
        assert len(pkg.relevant_sops) > 0
    if "regulatory" in config.RETRIEVAL_CONFIG[agent_name]:
        assert len(pkg.regulatory_context) > 0

    # similar_capas always ranked descending by similarity_score, capped
    scores = [c.similarity_score or 0.0 for c in pkg.similar_capas]
    assert scores == sorted(scores, reverse=True)
    assert len(pkg.similar_capas) <= config.MAX_SIMILAR_CAPAS


@pytest.mark.asyncio
async def test_fallback_ranked_below_real_vector_hits(repo):
    """Sub-Phase 2b checkpoint: when sql has no site/category to match on
    (fallback = most-recent-CAPAs junk), a genuinely relevant vector hit
    must still outrank it in the merged similar_capas list."""
    capa_input = CAPARecord(
        tenant_id="TENANT_ACERTECH",
        capa_id="CAPA_CHECKPOINT2B_FALLBACK",
        title="Wire rope failure on overhead crane recurring",
        description="wire rope failure on overhead crane recurring",
        source_module="Inspection",
    )
    pkg = await get_context_package(capa_input, "evaluator", repo)

    assert pkg.similar_capas_is_fallback is True
    fallback_score = 0.1
    real_hits = [c for c in pkg.similar_capas if c.similarity_score > fallback_score]
    assert len(real_hits) > 0
    # every real hit must come before every fallback-scored entry in the list
    fallback_seen = False
    for c in pkg.similar_capas:
        if c.similarity_score == fallback_score:
            fallback_seen = True
        elif fallback_seen:
            pytest.fail("a higher-scored entry appeared after a fallback-scored one")
