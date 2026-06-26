"""Unit tests for agents/evaluator.py's _derive_from_classification() — the
pure-Python derivation of root_cause_linkage/preventive_value/
training_overreliance from Call B's classification + config's taxonomy
tables. No LLM, no network. See phases/phase4.md decision 2."""

import sys
from pathlib import Path
from typing import get_args

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import config  # noqa: E402
from agents.evaluator import _CallBResult, _derive_from_classification  # noqa: E402
from models.schemas import ActionTheme  # noqa: E402

_THEMES = list(get_args(ActionTheme))
_CATEGORIES = list(config.ROOT_CAUSE_CATEGORY_THEME_MAP.keys())


@pytest.mark.parametrize("theme", _THEMES)
@pytest.mark.parametrize("category", _CATEGORIES)
def test_derivation_matches_config_tables(theme, category):
    classification = _CallBResult(
        action_theme=theme, addresses_root_cause=True, addresses_root_cause_reason="addresses it"
    )
    result = _derive_from_classification(classification, category)

    expected_linkage = theme in config.ROOT_CAUSE_CATEGORY_THEME_MAP[category]
    assert result["root_cause_linkage"].passed == expected_linkage

    expected_preventive = (
        config.CONTROL_STRENGTH_RUBRIC[theme] >= config.PREVENTIVE_VALUE_PASS_THRESHOLD
    )
    assert result["preventive_value"].passed == expected_preventive

    expected_overreliance = theme != "Training" or category in config.TRAINING_SUFFICIENT_CATEGORIES
    assert result["training_overreliance"].passed == expected_overreliance


def test_addresses_root_cause_false_fails_linkage_even_if_theme_compatible():
    classification = _CallBResult(
        action_theme="Engineering Control",
        addresses_root_cause=False,
        addresses_root_cause_reason="generic, doesn't target the cited controls",
    )
    result = _derive_from_classification(classification, "CAT_EQUIPMENT_FAULT")
    assert result["root_cause_linkage"].passed is False


def test_training_only_on_training_gap_category_passes_overreliance():
    classification = _CallBResult(
        action_theme="Training", addresses_root_cause=True, addresses_root_cause_reason="x"
    )
    result = _derive_from_classification(classification, "CAT_TRAINING_GAP")
    assert result["training_overreliance"].passed is True


def test_training_only_on_equipment_fault_category_fails_overreliance():
    classification = _CallBResult(
        action_theme="Training", addresses_root_cause=True, addresses_root_cause_reason="x"
    )
    result = _derive_from_classification(classification, "CAT_EQUIPMENT_FAULT")
    assert result["training_overreliance"].passed is False


def test_engineering_control_always_passes_preventive_value():
    classification = _CallBResult(
        action_theme="Engineering Control", addresses_root_cause=True, addresses_root_cause_reason="x"
    )
    result = _derive_from_classification(classification, "CAT_EQUIPMENT_FAULT")
    assert result["preventive_value"].passed is True


def test_unknown_category_has_no_compatible_themes():
    classification = _CallBResult(
        action_theme="Engineering Control", addresses_root_cause=True, addresses_root_cause_reason="x"
    )
    result = _derive_from_classification(classification, None)
    assert result["root_cause_linkage"].passed is False
