"""Pure unit tests for engines/scoring_engine.py — no LLM, no network, no DB.
See phases/phase4.md."""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import config  # noqa: E402
from engines import scoring_engine  # noqa: E402
from models.schemas import DimensionResult, EvaluationResult, RecurrenceResult  # noqa: E402

_PASS = DimensionResult(passed=True, reason="ok")
_FAIL = DimensionResult(passed=False, reason="bad")
_NO_RECURRENCE = RecurrenceResult(recurrence_detected=False, prior_occurrence_count=0)


def _all_pass() -> EvaluationResult:
    return EvaluationResult(**{dim: _PASS for dim in config.DIMENSION_WEIGHTS})


def _all_fail() -> EvaluationResult:
    return EvaluationResult(**{dim: _FAIL for dim in config.DIMENSION_WEIGHTS})


def test_dimension_weights_sum_to_one():
    assert sum(config.DIMENSION_WEIGHTS.values()) == pytest.approx(1.0)


def test_all_pass_scores_100_none_weakness():
    result = scoring_engine.compute_score(_all_pass(), _NO_RECURRENCE)
    assert result.score == 100
    assert result.weakness_level == "None"
    assert result.failed_dimensions == []


def test_all_fail_scores_0_critical_weakness():
    result = scoring_engine.compute_score(_all_fail(), _NO_RECURRENCE)
    assert result.score == 0
    assert result.weakness_level == "Critical"
    assert set(result.failed_dimensions) == set(config.DIMENSION_WEIGHTS)


def test_failing_one_dimension_drops_score_by_its_weight():
    eval_result = _all_pass().model_copy(update={"clarity": _FAIL})
    result = scoring_engine.compute_score(eval_result, _NO_RECURRENCE)
    assert result.score == 100 - round(config.DIMENSION_WEIGHTS["clarity"] * 100)
    assert result.failed_dimensions == ["clarity"]


@pytest.mark.parametrize(
    "score,expected_level",
    [(100, "None"), (85, "None"), (84, "Low"), (70, "Low"), (69, "Medium"),
     (50, "Medium"), (49, "High"), (30, "High"), (29, "Critical"), (0, "Critical")],
)
def test_weakness_level_boundaries(score, expected_level):
    assert scoring_engine._weakness_level(score) == expected_level


def test_recurrence_same_approach_failed_applies_heaviest_penalty():
    recurrence = RecurrenceResult(
        recurrence_detected=True,
        prior_occurrence_count=2,
        new_actions_are_same_as_past=True,
        past_actions_were_effective=False,
    )
    result = scoring_engine.compute_score(_all_pass(), recurrence)
    assert result.score == 100 - config.RECURRENCE_PENALTIES["same_approach_failed"]


def test_recurrence_same_approach_unknown_effectiveness_applies_medium_penalty():
    recurrence = RecurrenceResult(
        recurrence_detected=True,
        prior_occurrence_count=1,
        new_actions_are_same_as_past=True,
        past_actions_were_effective=None,
    )
    result = scoring_engine.compute_score(_all_pass(), recurrence)
    assert result.score == 100 - config.RECURRENCE_PENALTIES["same_approach_unknown"]


def test_recurrence_comparison_unavailable_does_not_silently_disable_penalty():
    """Regression for the reference build's analysis.md-flagged bug: when the
    comparison itself fails (new_actions_are_same_as_past is None), the
    penalty must still apply, not silently vanish."""
    recurrence = RecurrenceResult(
        recurrence_detected=True,
        prior_occurrence_count=3,
        new_actions_are_same_as_past=None,
        past_actions_were_effective=None,
    )
    result = scoring_engine.compute_score(_all_pass(), recurrence)
    assert result.score == 100 - config.RECURRENCE_PENALTIES["comparison_unavailable"]


def test_recurrence_new_approach_against_failed_category_applies_penalty():
    recurrence = RecurrenceResult(
        recurrence_detected=True,
        prior_occurrence_count=2,
        new_actions_are_same_as_past=False,
        past_actions_were_effective=False,
    )
    result = scoring_engine.compute_score(_all_pass(), recurrence)
    assert result.score == 100 - config.RECURRENCE_PENALTIES["new_approach_failed_category"]


def test_recurrence_new_approach_against_effective_category_applies_no_penalty():
    recurrence = RecurrenceResult(
        recurrence_detected=True,
        prior_occurrence_count=2,
        new_actions_are_same_as_past=False,
        past_actions_were_effective=True,
    )
    result = scoring_engine.compute_score(_all_pass(), recurrence)
    assert result.score == 100


def test_score_clamps_at_zero_not_negative():
    recurrence = RecurrenceResult(
        recurrence_detected=True,
        prior_occurrence_count=5,
        new_actions_are_same_as_past=True,
        past_actions_were_effective=False,
    )
    result = scoring_engine.compute_score(_all_fail(), recurrence)
    assert result.score == 0
