"""Checkpoint 3 — Generator Agent.

10 varied CAPARecord + requested_action_type inputs against the live seeded
capa_assist DB + ChromaDB + live LLM (Groq). Self-skips (via the `repo`
fixture) if the dev DB is unreachable. See phases/phase3.md.
"""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import agents.generator as generator_mod  # noqa: E402
from models.schemas import AgentInput, CAPARecord, ExistingActionRef  # noqa: E402
from retrieval.context_retrieval import get_context_package  # noqa: E402


def _capa(**overrides) -> CAPARecord:
    base = dict(
        tenant_id="TENANT_ACERTECH",
        capa_id="CAPA_CHECKPOINT3_TEST",
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
    ("containment", _capa(requested_action_type="Containment")),
    ("corrective", _capa(requested_action_type="Corrective")),
    ("preventive", _capa(requested_action_type="Preventive")),
    ("risk_mitigation", _capa(requested_action_type="Risk Mitigation")),
    ("missing_severity", _capa(severity=None, requested_action_type="Corrective")),
    ("missing_site", _capa(site_id=None, root_cause_category=None, requested_action_type="Corrective")),
    (
        "incident_source",
        _capa(
            source_module="Incident",
            title="LTI on warehouse floor",
            description="A warehouse associate sustained a fracture after being struck by a forklift.",
            requested_action_type="Corrective",
        ),
    ),
    (
        "with_missing_controls",
        _capa(missing_controls=["Pedestrian barrier", "Forklift proximity alarm"], requested_action_type="Preventive"),
    ),
    (
        "with_existing_actions",
        _capa(
            existing_actions=[
                ExistingActionRef(type="Corrective", description="Replace the failed wire rope on OC-001.")
            ],
            requested_action_type="Preventive",
        ),
    ),
    (
        "minimal_input",
        CAPARecord(
            tenant_id="TENANT_ACERTECH",
            capa_id="CAPA_CHECKPOINT3_MINIMAL",
            title="Spill in chemical storage",
            description="Minor chemical spill reported in bay 3.",
            source_module="Near Miss",
            requested_action_type="Containment",
        ),
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,capa_input", CASES, ids=[c[0] for c in CASES])
async def test_generator_checkpoint(name, capa_input, repo, tenant):
    context_package = await get_context_package(capa_input, "generator", repo)
    agent_input = AgentInput(
        capa_input=capa_input,
        context_package=context_package,
        action_type=capa_input.requested_action_type,
    )

    actions = await generator_mod.run(agent_input, repo, num_actions=2)

    assert 1 <= len(actions) <= 2
    for action in actions:
        assert action.type == capa_input.requested_action_type
        assert len(action.requirements) >= 1
        for req in action.requirements:
            if req.mandatory:
                assert len(req.options) == 1
            else:
                assert 2 <= len(req.options) <= 5
        assert len(action.required_evidence) >= 2
        assert action.confidence_level in ("High", "Medium", "Low")
        assert action.linked_root_cause
        generator_mod._validate_due_date_windows([action])

    if capa_input.existing_actions:
        existing_texts = {ea.description for ea in capa_input.existing_actions}
        for action in actions:
            assert action.title not in existing_texts, (
                "Generated action should build on existing_actions, not repeat one verbatim"
            )
