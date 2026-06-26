"""Sub-Phase 2b — build_employee_question() must vary with root_cause_category
instead of always asking the same fixed question. Pure unit test, no network.
"""

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from retrieval.nl2sql import build_employee_question  # noqa: E402


def test_question_varies_by_category():
    q1 = build_employee_question("SITE_01", "CAT_TRAINING_GAP")
    q2 = build_employee_question("SITE_01", "CAT_EQUIPMENT_FAULT")
    q3 = build_employee_question("SITE_01", "CAT_MANAGEMENT_SYSTEM_WEAKNESS")
    assert q1 != q2 != q3
    assert "training" in q1.lower()
    assert "maintenance" in q2.lower() or "engineering" in q2.lower()


def test_question_falls_back_generic_when_no_category():
    q = build_employee_question("SITE_01", None)
    assert q == "List employees and their roles at site SITE_01."


def test_question_falls_back_generic_when_unknown_category():
    q = build_employee_question("SITE_01", "CAT_NOT_A_REAL_CATEGORY")
    assert q == "List employees and their roles at site SITE_01."
