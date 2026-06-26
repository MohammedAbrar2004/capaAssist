"""Pure unit tests for agents/explainability.py — mocks call_llm, no network.
See phases/phase6.md."""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import agents.explainability as explainability_mod  # noqa: E402
from models.schemas import DimensionResult, EvaluationResult, RecurrenceResult, ScoringResult  # noqa: E402


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


def _scoring(failed: list[str] = (), recurrence: RecurrenceResult = None) -> ScoringResult:
    return ScoringResult(
        score=55,
        weakness_level="Medium",
        failed_dimensions=list(failed),
        recurrence=recurrence or RecurrenceResult(recurrence_detected=False, prior_occurrence_count=0),
    )


@pytest.mark.asyncio
async def test_run_renders_org_name_and_failed_dims(monkeypatch):
    captured = {}

    async def fake_call_llm(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        captured["model"] = kwargs["model"]
        captured["temperature"] = kwargs["temperature"]
        return "This action lacks a clear owner and due date. Fix: assign an owner and set a deadline."

    monkeypatch.setattr(explainability_mod, "call_llm", fake_call_llm)

    eval_result = _evaluation(failed=["ownership", "due_date_quality"])
    scoring = _scoring(failed=["ownership", "due_date_quality"])

    explanation = await explainability_mod.run(eval_result, scoring, "Train the team.")

    assert "ownership reason" in captured["prompt"]
    assert "due_date_quality reason" in captured["prompt"]
    assert explainability_mod.config.ORG_NAME in captured["prompt"]
    assert captured["model"] == explainability_mod.config.LIGHT_MODEL
    assert captured["temperature"] == 0.4
    assert explanation.startswith("This action lacks")


@pytest.mark.asyncio
async def test_run_omits_recurrence_when_not_detected(monkeypatch):
    captured = {}

    async def fake_call_llm(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return "ok"

    monkeypatch.setattr(explainability_mod, "call_llm", fake_call_llm)

    eval_result = _evaluation()
    scoring = _scoring(recurrence=RecurrenceResult(recurrence_detected=False, prior_occurrence_count=0))

    await explainability_mod.run(eval_result, scoring, "Train the team.")

    assert "Recurrence flag" not in captured["prompt"]


@pytest.mark.asyncio
async def test_run_includes_recurrence_when_detected(monkeypatch):
    captured = {}

    async def fake_call_llm(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return "ok"

    monkeypatch.setattr(explainability_mod, "call_llm", fake_call_llm)

    eval_result = _evaluation()
    scoring = _scoring(
        recurrence=RecurrenceResult(
            recurrence_detected=True,
            prior_occurrence_count=3,
            recurrence_warning="This approach failed twice before at this site.",
        )
    )

    await explainability_mod.run(eval_result, scoring, "Train the team.")

    assert "This approach failed twice before at this site." in captured["prompt"]


@pytest.mark.asyncio
async def test_run_falls_back_on_llm_failure(monkeypatch):
    async def failing_call_llm(messages, **kwargs):
        raise RuntimeError("all tiers exhausted")

    monkeypatch.setattr(explainability_mod, "call_llm", failing_call_llm)

    eval_result = _evaluation(failed=["ownership", "due_date_quality", "clarity"])
    scoring = _scoring(failed=["ownership", "due_date_quality", "clarity"])

    explanation = await explainability_mod.run(eval_result, scoring, "Train the team.")

    assert "55/100" in explanation
    assert "Medium" in explanation
    assert "ownership" in explanation
    assert "due_date_quality" in explanation
    assert "clarity" in explanation


@pytest.mark.asyncio
async def test_run_fallback_never_raises_with_no_failed_dimensions(monkeypatch):
    async def failing_call_llm(messages, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(explainability_mod, "call_llm", failing_call_llm)

    eval_result = _evaluation()
    scoring = _scoring(failed=[])

    explanation = await explainability_mod.run(eval_result, scoring, "Train the team.")

    assert "several quality checks" in explanation
