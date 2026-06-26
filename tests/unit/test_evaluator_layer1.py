"""Unit tests for agents/evaluator.py's Layer 1 regex rules — no LLM, no
network. See phases/phase4.md."""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from agents.evaluator import _rule_based  # noqa: E402


def test_ownership_passes_with_role_noun():
    result = _rule_based("Assigned to the Maintenance Supervisor for completion.")
    assert result["ownership"].passed is True


def test_ownership_fails_with_bare_team_name():
    result = _rule_based("The EHS team will handle this.")
    assert result["ownership"].passed is False


def test_due_date_passes_with_concrete_date():
    result = _rule_based("Complete by 2026-08-01.")
    assert result["due_date_quality"].passed is True


def test_due_date_passes_with_day_count():
    result = _rule_based("Complete within 30 days.")
    assert result["due_date_quality"].passed is True


def test_due_date_fails_with_vague_urgency_only():
    result = _rule_based("Complete this ASAP.")
    assert result["due_date_quality"].passed is False


def test_evidence_passes_with_specific_artifact():
    result = _rule_based("Attach a signed inspection report as evidence.")
    assert result["evidence_requirement"].passed is True


def test_evidence_fails_with_bare_report_reference():
    result = _rule_based("File a report when done.")
    assert result["evidence_requirement"].passed is False


def test_effectiveness_check_passes_with_verification_method():
    result = _rule_based("Verify effectiveness via re-inspection at 30 days.")
    assert result["effectiveness_check"].passed is True


def test_effectiveness_check_fails_with_no_verification_language():
    result = _rule_based("Replace the part.")
    assert result["effectiveness_check"].passed is False


def test_train_the_team_fails_ownership_due_date_evidence_and_effectiveness():
    result = _rule_based("Train the team.")
    assert result["ownership"].passed is False
    assert result["due_date_quality"].passed is False
    assert result["evidence_requirement"].passed is False
    assert result["effectiveness_check"].passed is False


@pytest.mark.parametrize("dim", ["ownership", "due_date_quality", "evidence_requirement", "effectiveness_check"])
def test_strong_action_passes_all_layer1_dims(dim):
    text = (
        "Assigned to the Maintenance Supervisor. Complete within 30 days. "
        "Attach a signed inspection report as evidence. Verify effectiveness via "
        "re-inspection at 30 days."
    )
    result = _rule_based(text)
    assert result[dim].passed is True
