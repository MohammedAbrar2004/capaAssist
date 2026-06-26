"""Checkpoint 5 — Improver Agent.

Ground-truth test (phases/phase5.md / reference/plan.md Phase 4 testing
checkpoint): take weak action text, evaluate it, improve it, re-evaluate the
improved text — improved score must exceed the original score. Live LLM +
live DB + live ChromaDB. Self-skips if the dev DB is unreachable.
"""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import agents.evaluator as evaluator_mod  # noqa: E402
import agents.improver as improver_mod  # noqa: E402
from engines import scoring_engine  # noqa: E402
from models.schemas import AgentInput, CAPARecord  # noqa: E402
from retrieval.context_retrieval import get_context_package  # noqa: E402


def _capa(**overrides) -> CAPARecord:
    base = dict(
        tenant_id="TENANT_ACERTECH",
        capa_id="CAPA_CHECKPOINT5_TEST",
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


WEAK_CASES = [
    ("vague_training_only", _capa(actions=["Train the team."])),
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
        "no_due_date_no_evidence",
        _capa(actions=["Replace the frayed wire rope on the crane."]),
    ),
]


async def _evaluate(capa_input, action_text, repo):
    context_package = await get_context_package(capa_input, "evaluator", repo)
    agent_input = AgentInput(
        capa_input=capa_input, context_package=context_package, action_text=action_text
    )
    evaluation, recurrence = await evaluator_mod.run(agent_input, repo)
    scoring = scoring_engine.compute_score(evaluation, recurrence)
    return agent_input, evaluation, recurrence, scoring


@pytest.mark.asyncio
@pytest.mark.parametrize("name,capa_input", WEAK_CASES, ids=[c[0] for c in WEAK_CASES])
async def test_improver_checkpoint(name, capa_input, repo, tenant):
    original_text = capa_input.actions[0]
    agent_input, evaluation, recurrence, original_scoring = await _evaluate(
        capa_input, original_text, repo
    )

    improver_context = await get_context_package(capa_input, "improver", repo)
    improver_input = AgentInput(
        capa_input=capa_input, context_package=improver_context, action_text=original_text
    )
    result = await improver_mod.run(improver_input, evaluation, recurrence)

    assert result.improved_action_title
    assert result.improved_action_description
    assert len(result.changes_explained) >= 1

    structural_gap = not (
        evaluation.root_cause_linkage.passed
        and evaluation.preventive_value.passed
        and evaluation.training_overreliance.passed
    )
    # Python's gate is deterministic (no additional_actions unless the
    # structural trigger fired) but compliance with the *request* for them
    # is still an LLM call, so only assert the upper bound here, not a
    # hard minimum, to avoid live-LLM flakiness.
    assert len(result.additional_actions) <= improver_mod._MAX_ADDITIONAL_ACTIONS
    if not structural_gap:
        assert result.additional_actions == []

    improved_text = f"{result.improved_action_title}: {result.improved_action_description}"
    _, _, _, improved_scoring = await _evaluate(capa_input, improved_text, repo)

    assert improved_scoring.score > original_scoring.score, (
        f"{name}: improved score {improved_scoring.score} did not exceed "
        f"original score {original_scoring.score}. Changes: {result.changes_explained}"
    )
