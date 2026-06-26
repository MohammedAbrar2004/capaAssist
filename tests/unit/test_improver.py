"""Pure unit tests for agents/improver.py — mocks call_llm_json, no network.
See phases/phase5.md."""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import agents.improver as improver_mod  # noqa: E402
from models.schemas import (  # noqa: E402
    AgentInput,
    CAPARecord,
    ContextPackage,
    DimensionResult,
    EvaluationResult,
    GeneratedAction,
    ImproverResult,
    RecurrenceResult,
)


def _capa(**overrides) -> CAPARecord:
    base = dict(
        tenant_id="TENANT_ACERTECH",
        capa_id="CAPA_IMPROVER_TEST",
        title="Test",
        description="Test description",
        source_module="Incident",
        actions=["Train the team."],
    )
    base.update(overrides)
    return CAPARecord(**base)


def _agent_input(capa: CAPARecord) -> AgentInput:
    return AgentInput(
        capa_input=capa,
        context_package=ContextPackage(problem_summary=capa.description),
        action_text=capa.actions[0],
    )


def _evaluation(failed: list[str] = ()) -> EvaluationResult:
    def dim(name: str) -> DimensionResult:
        passed = name not in failed
        return DimensionResult(passed=passed, reason=f"{name} reason")

    return EvaluationResult(
        clarity=dim("clarity"),
        specificity=dim("specificity"),
        root_cause_linkage=dim("root_cause_linkage"),
        preventive_value=dim("preventive_value"),
        ownership=dim("ownership"),
        due_date_quality=dim("due_date_quality"),
        evidence_requirement=dim("evidence_requirement"),
        effectiveness_check=dim("effectiveness_check"),
        training_overreliance=dim("training_overreliance"),
    )


_NO_RECURRENCE = RecurrenceResult(recurrence_detected=False, prior_occurrence_count=0)


def _llm_result(**overrides):
    class _Result:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, v)

    base = dict(
        improved_action_title="Replace failed wire rope",
        improved_action_description="Maintenance Supervisor to replace the rope by 2026-12-01...",
        changes_explained=["Added an owner.", "Added a due date."],
        additional_actions=[],
    )
    base.update(overrides)
    return _Result(base)


def _generated_action(**overrides) -> GeneratedAction:
    base = dict(
        type="Preventive",
        title="Install wire-rope condition-monitoring sensor",
        requirements=[
            {"label": "Catch wear before failure", "mandatory": True,
             "options": [{"text": "Install a condition-monitoring sensor."}]}
        ],
        recommended_owner_role="Maintenance Supervisor",
        recommended_due_date="2026-12-01",
        required_evidence=["Work order", "Sensor calibration record"],
        effectiveness_check_method="Review sensor data monthly for 90 days.",
        rationale="Engineering control closes the gap training alone cannot.",
        linked_root_cause="Wire rope inspection criteria not specified.",
        confidence_level="Medium",
    )
    base.update(overrides)
    return GeneratedAction(**base)


@pytest.mark.asyncio
async def test_run_returns_improver_result(monkeypatch):
    capa = _capa()
    agent_input = _agent_input(capa)
    eval_result = _evaluation(failed=["ownership", "due_date_quality"])

    captured = {}

    async def fake_call_llm_json(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return _llm_result()

    monkeypatch.setattr(improver_mod, "call_llm_json", fake_call_llm_json)

    result = await improver_mod.run(agent_input, eval_result, _NO_RECURRENCE)

    assert isinstance(result, ImproverResult)
    assert result.original_action_text == "Train the team."
    assert result.improved_action_title == "Replace failed wire rope"
    assert len(result.changes_explained) == 2
    assert "ownership" in captured["prompt"]
    assert "due_date_quality" in captured["prompt"]
    # Passing dimensions are not gaps to fix — must not be listed.
    assert "clarity reason" not in captured["prompt"]


@pytest.mark.asyncio
async def test_run_renders_edit_instruction(monkeypatch):
    capa = _capa(edit_instruction="Focus on tightening the due date.")
    agent_input = _agent_input(capa)
    eval_result = _evaluation(failed=["due_date_quality"])

    captured = {}

    async def fake_call_llm_json(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return _llm_result()

    monkeypatch.setattr(improver_mod, "call_llm_json", fake_call_llm_json)

    await improver_mod.run(agent_input, eval_result, _NO_RECURRENCE)

    assert "Focus on tightening the due date." in captured["prompt"]


@pytest.mark.asyncio
async def test_run_renders_recurrence_warning(monkeypatch):
    capa = _capa()
    agent_input = _agent_input(capa)
    eval_result = _evaluation()
    recurrence = RecurrenceResult(
        recurrence_detected=True,
        prior_occurrence_count=3,
        recurrence_warning="This approach failed twice before at this site.",
    )

    captured = {}

    async def fake_call_llm_json(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return _llm_result()

    monkeypatch.setattr(improver_mod, "call_llm_json", fake_call_llm_json)

    await improver_mod.run(agent_input, eval_result, recurrence)

    assert "This approach failed twice before at this site." in captured["prompt"]


@pytest.mark.asyncio
async def test_run_requires_action_text():
    capa = _capa(actions=None)
    agent_input = AgentInput(
        capa_input=capa, context_package=ContextPackage(problem_summary="x"), action_text=None
    )
    with pytest.raises(ValueError):
        await improver_mod.run(agent_input, _evaluation(), _NO_RECURRENCE)


@pytest.mark.asyncio
async def test_run_rejects_empty_changes_explained(monkeypatch):
    async def fake_call_llm_json(messages, **kwargs):
        return _llm_result(changes_explained=[])

    monkeypatch.setattr(improver_mod, "call_llm_json", fake_call_llm_json)

    capa = _capa()
    agent_input = _agent_input(capa)
    with pytest.raises(Exception):
        await improver_mod.run(agent_input, _evaluation(), _NO_RECURRENCE)


@pytest.mark.asyncio
async def test_run_requests_additional_actions_when_structural_gap(monkeypatch):
    """training_overreliance failing is one of the 3 objective triggers —
    Python must ask for (and pass through) additional_actions."""
    capa = _capa()
    agent_input = _agent_input(capa)
    eval_result = _evaluation(failed=["training_overreliance", "preventive_value"])

    captured = {}

    async def fake_call_llm_json(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return _llm_result(additional_actions=[_generated_action()])

    monkeypatch.setattr(improver_mod, "call_llm_json", fake_call_llm_json)

    result = await improver_mod.run(agent_input, eval_result, _NO_RECURRENCE)

    assert len(result.additional_actions) == 1
    assert result.additional_actions[0].type == "Preventive"
    assert "needs_additional_actions" not in captured["prompt"]  # not a raw flag leak
    assert "training_overreliance reason" in captured["prompt"]


@pytest.mark.asyncio
async def test_run_drops_additional_actions_when_no_structural_gap(monkeypatch):
    """Only clarity/ownership-style gaps failed — none of the 3 structural
    dimensions. Even if the LLM returns suggestions anyway, Python must
    drop them (objective gate, not an LLM judgment call)."""
    capa = _capa()
    agent_input = _agent_input(capa)
    eval_result = _evaluation(failed=["clarity", "ownership"])

    async def fake_call_llm_json(messages, **kwargs):
        return _llm_result(additional_actions=[_generated_action()])

    monkeypatch.setattr(improver_mod, "call_llm_json", fake_call_llm_json)

    result = await improver_mod.run(agent_input, eval_result, _NO_RECURRENCE)

    assert result.additional_actions == []


@pytest.mark.asyncio
async def test_run_caps_additional_actions_at_max(monkeypatch):
    capa = _capa()
    agent_input = _agent_input(capa)
    eval_result = _evaluation(failed=["root_cause_linkage"])

    async def fake_call_llm_json(messages, **kwargs):
        return _llm_result(
            additional_actions=[_generated_action(), _generated_action(), _generated_action()]
        )

    monkeypatch.setattr(improver_mod, "call_llm_json", fake_call_llm_json)

    result = await improver_mod.run(agent_input, eval_result, _NO_RECURRENCE)

    assert len(result.additional_actions) == improver_mod._MAX_ADDITIONAL_ACTIONS
