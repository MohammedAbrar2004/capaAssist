"""scoring_engine.py — deterministic scoring (Phase 4). No LLM import here at
all: this module turns an already-judged EvaluationResult + RecurrenceResult
into a score. See phases/phase4.md.
"""

import config
from models.schemas import EvaluationResult, RecurrenceResult, ScoringResult, WeaknessLevel


def _weakness_level(score: int) -> WeaknessLevel:
    for lo, hi, level, _behavior in config.WEAKNESS_THRESHOLDS:
        if lo <= score <= hi:
            return level
    return "Critical"


def _recurrence_penalty(recurrence: RecurrenceResult) -> float:
    if not recurrence.recurrence_detected:
        return 0.0

    penalties = config.RECURRENCE_PENALTIES
    same = recurrence.new_actions_are_same_as_past
    effective = recurrence.past_actions_were_effective

    if same is None:
        # Comparison itself failed/unavailable — don't silently let the
        # recurrence signal disappear (the bug analysis.md flagged in the
        # reference build).
        return penalties["comparison_unavailable"]
    if same:
        if effective is False:
            return penalties["same_approach_failed"]
        return penalties["same_approach_unknown"]
    # Genuinely a new approach, but this category has a known-failed history.
    if effective is False:
        return penalties["new_approach_failed_category"]
    return 0.0


def compute_score(eval_result: EvaluationResult, recurrence: RecurrenceResult) -> ScoringResult:
    raw = 0.0
    failed: list[str] = []
    for dim, weight in config.DIMENSION_WEIGHTS.items():
        result = getattr(eval_result, dim)
        if result.passed:
            raw += weight * 100
        else:
            failed.append(dim)

    penalty = _recurrence_penalty(recurrence)
    score = max(0.0, raw - penalty)
    score_int = round(score)

    return ScoringResult(
        score=score_int,
        weakness_level=_weakness_level(score_int),
        failed_dimensions=failed,
        recurrence=recurrence,
    )
