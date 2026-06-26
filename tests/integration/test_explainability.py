"""Checkpoint 6 — Explainability Agent.

Structural spot-check (no numeric ground truth like the Improver's "score
must increase" — explanation quality is checked structurally): evaluate a
weak action, then explain it. Assert non-empty, under a generous word
ceiling, no raw dimension snake_case tokens, no JSON/markdown. Live LLM +
live DB + live ChromaDB. Self-skips if the dev DB is unreachable.
"""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import agents.evaluator as evaluator_mod  # noqa: E402
import agents.explainability as explainability_mod  # noqa: E402
from engines import scoring_engine  # noqa: E402
from models.schemas import ALL_DIMENSIONS, AgentInput, CAPARecord  # noqa: E402
from retrieval.context_retrieval import get_context_package  # noqa: E402


def _capa(**overrides) -> CAPARecord:
    base = dict(
        tenant_id="TENANT_ACERTECH",
        capa_id="CAPA_CHECKPOINT6_TEST",
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
    ("no_owner", _capa(actions=["Replace the wire rope within 14 days."])),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,capa_input", WEAK_CASES, ids=[c[0] for c in WEAK_CASES])
async def test_explainability_checkpoint(name, capa_input, repo, tenant):
    action_text = capa_input.actions[0]
    context_package = await get_context_package(capa_input, "evaluator", repo)
    agent_input = AgentInput(
        capa_input=capa_input, context_package=context_package, action_text=action_text
    )
    evaluation, recurrence = await evaluator_mod.run(agent_input, repo)
    scoring = scoring_engine.compute_score(evaluation, recurrence)

    explanation = await explainability_mod.run(evaluation, scoring, action_text)

    assert explanation.strip()
    word_count = len(explanation.split())
    assert word_count <= 180, f"{name}: explanation ran {word_count} words: {explanation}"

    assert "{" not in explanation and "}" not in explanation
    assert "\n-" not in explanation and "\n*" not in explanation

    for dim in ALL_DIMENSIONS:
        assert dim not in explanation, f"{name}: raw dimension token {dim!r} leaked into prose"
