"""Unit tests for services/eval_cache.py — pure in-memory, no LLM/DB.
See phases/phase5.md decision 3."""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import config  # noqa: E402
import services.eval_cache as eval_cache  # noqa: E402
from models.schemas import DimensionResult, EvaluationResult, RecurrenceResult  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_cache():
    eval_cache._cache.clear()
    yield
    eval_cache._cache.clear()


def _pair() -> tuple[EvaluationResult, RecurrenceResult]:
    pass_dim = DimensionResult(passed=True, reason="ok")
    evaluation = EvaluationResult(
        clarity=pass_dim,
        specificity=pass_dim,
        root_cause_linkage=pass_dim,
        preventive_value=pass_dim,
        ownership=pass_dim,
        due_date_quality=pass_dim,
        evidence_requirement=pass_dim,
        effectiveness_check=pass_dim,
        training_overreliance=pass_dim,
    )
    recurrence = RecurrenceResult(recurrence_detected=False, prior_occurrence_count=0)
    return evaluation, recurrence


def test_get_miss_returns_none():
    key = eval_cache.make_key("T1", "CAPA1", None, "Train the team.")
    assert eval_cache.get(key) is None


def test_put_then_get_round_trips():
    key = eval_cache.make_key("T1", "CAPA1", "ACT1", "Train the team.")
    value = _pair()
    eval_cache.put(key, value)
    assert eval_cache.get(key) == value


def test_make_key_prefers_action_id_over_text():
    key_a = eval_cache.make_key("T1", "CAPA1", "ACT1", "Text A")
    key_b = eval_cache.make_key("T1", "CAPA1", "ACT1", "Text B — different text, same action_id")
    assert key_a == key_b


def test_make_key_falls_back_to_text_hash_when_no_action_id():
    key_a = eval_cache.make_key("T1", "CAPA1", None, "Train the team.")
    key_b = eval_cache.make_key("T1", "CAPA1", None, "Replace the wire rope.")
    assert key_a != key_b


def test_lru_eviction_at_capacity():
    value = _pair()
    for i in range(config.EVAL_CACHE_MAX_ENTRIES + 1):
        eval_cache.put(eval_cache.make_key("T1", "CAPA1", f"ACT{i}", "text"), value)

    assert len(eval_cache._cache) == config.EVAL_CACHE_MAX_ENTRIES
    assert eval_cache.get(eval_cache.make_key("T1", "CAPA1", "ACT0", "text")) is None
    assert eval_cache.get(eval_cache.make_key("T1", "CAPA1", "ACT1", "text")) is not None


def test_get_touches_lru_order():
    value = _pair()
    key0 = eval_cache.make_key("T1", "CAPA1", "ACT0", "text")
    eval_cache.put(key0, value)
    for i in range(1, config.EVAL_CACHE_MAX_ENTRIES):
        eval_cache.put(eval_cache.make_key("T1", "CAPA1", f"ACT{i}", "text"), value)

    # Touch key0 so it's no longer the oldest entry.
    eval_cache.get(key0)

    # One more insert should evict the new oldest (ACT1), not key0.
    eval_cache.put(eval_cache.make_key("T1", "CAPA1", "ACTNEW", "text"), value)

    assert eval_cache.get(key0) is not None
    assert eval_cache.get(eval_cache.make_key("T1", "CAPA1", "ACT1", "text")) is None
