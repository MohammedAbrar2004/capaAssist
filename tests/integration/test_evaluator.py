"""Checkpoint 4 — Evaluator Agent.

Live LLM + live DB + live ChromaDB. Self-skips (via the `repo` fixture) if
the dev DB is unreachable. Strong/weak fixtures carry equal context richness
(site_id + root_cause_category set on every case) — the reference build's
analysis.md flagged asymmetric fixtures as a confound in its own checkpoint,
avoided here. See phases/phase4.md.
"""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import agents.evaluator as evaluator_mod  # noqa: E402
from engines import scoring_engine  # noqa: E402
from models.schemas import AgentInput, CAPARecord  # noqa: E402
from retrieval.context_retrieval import get_context_package  # noqa: E402


def _capa(**overrides) -> CAPARecord:
    base = dict(
        tenant_id="TENANT_ACERTECH",
        capa_id="CAPA_CHECKPOINT4_TEST",
        title="Wire rope fraying on overhead crane",
        description="Inspection found frayed wire rope strands on overhead crane OC-001.",
        source_module="Inspection",
        site_id="SITE_01",
        severity="High",
        capa_type="Corrective",
        root_cause_category="CAT_EQUIPMENT_FAULT",
        root_cause_statement="Wire rope inspection criteria not specified per ISO 4309.",
        contributing_factors=["No documented discard criteria for wire rope wear"],
        missing_controls=["Wire rope inspection checklist"],
    )
    base.update(overrides)
    return CAPARecord(**base)


CASES = [
    (
        "strong_engineering_control",
        _capa(
            actions=[
                "Assigned to the Maintenance Supervisor: install a wire-rope condition-"
                "monitoring sensor on Overhead Crane OC-001 and update the PM checklist "
                "to record bore-gauge strand counts. Complete within 45 days. Attach the "
                "signed inspection report and PM checklist as evidence. Verify "
                "effectiveness via re-inspection at 30 days post-completion."
            ]
        ),
    ),
    (
        "weak_vague_training_only",
        _capa(actions=["Train the team."]),
    ),
    (
        "training_only_on_equipment_fault",
        _capa(
            actions=[
                "Assigned to the Maintenance Supervisor: conduct a training session on "
                "wire rope inspection within 14 days. Attach the signed training "
                "attendance sheet as evidence. Verify effectiveness via a follow-up quiz."
            ]
        ),
    ),
    (
        "no_owner",
        _capa(
            actions=[
                "Replace the wire rope within 14 days. Attach the signed inspection "
                "report as evidence. Verify effectiveness via re-inspection at 30 days."
            ]
        ),
    ),
    (
        "training_sufficient_for_training_gap",
        _capa(
            root_cause_category="CAT_TRAINING_GAP",
            root_cause_statement="Operators were not trained on the updated LOTO procedure.",
            contributing_factors=["No record of LOTO refresher training"],
            actions=[
                "Assigned to the EHS Officer: deliver LOTO refresher training to all "
                "affected operators within 21 days. Attach the signed training "
                "attendance sheet as evidence. Verify effectiveness via a practical "
                "LOTO competency assessment at 30 days."
            ],
        ),
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,capa_input", CASES, ids=[c[0] for c in CASES])
async def test_evaluator_checkpoint(name, capa_input, repo, tenant):
    context_package = await get_context_package(capa_input, "evaluator", repo)
    agent_input = AgentInput(
        capa_input=capa_input,
        context_package=context_package,
        action_text=capa_input.actions[0],
    )

    evaluation, recurrence = await evaluator_mod.run(agent_input, repo)
    scoring = scoring_engine.compute_score(evaluation, recurrence)

    assert 0 <= scoring.score <= 100
    assert scoring.weakness_level in ("None", "Low", "Medium", "High", "Critical")

    if name == "strong_engineering_control":
        assert scoring.score >= 70
    elif name == "weak_vague_training_only":
        assert scoring.score < 50
        assert "clarity" in scoring.failed_dimensions or "specificity" in scoring.failed_dimensions
        assert "ownership" in scoring.failed_dimensions
    elif name == "training_only_on_equipment_fault":
        assert evaluation.training_overreliance.passed is False
        assert evaluation.preventive_value.passed is False
    elif name == "no_owner":
        assert evaluation.ownership.passed is False
    elif name == "training_sufficient_for_training_gap":
        assert evaluation.training_overreliance.passed is True
