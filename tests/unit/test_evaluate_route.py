"""Unit test for POST /capa/evaluate's plumbing (route shape, audit write,
persistence-only-when-action_id branch) — mocks evaluator.run/get_repository/
get_context_package so no network or DB is touched. See phases/phase4.md."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import api.routes as routes_mod  # noqa: E402
import orchestrator.dispatch as dispatch_mod  # noqa: E402
from main import app  # noqa: E402
from models.schemas import (  # noqa: E402
    CapaAction,
    ContextPackage,
    DimensionResult,
    EvaluationResult,
    RecurrenceResult,
)


def _evaluation() -> EvaluationResult:
    pass_dim = DimensionResult(passed=True, reason="ok")
    return EvaluationResult(
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


def _capa_action() -> CapaAction:
    return CapaAction.model_validate(
        dict(
            action_id="ACT_001",
            capa_id="CAPA_ROUTE_TEST",
            tenant_id="TENANT_ACERTECH",
            site_id="SITE_001",
            action_title="Replace failed wire rope",
            action_description="Replace and inspect.",
            priority_id="P1",
            capa_type_id="CT1",
            severity_id="S1",
            assigned_to="EMP_001",
            status_id="ST1",
            due_date="2026-12-01",
        )
    )


class _FakeRepo:
    def __init__(self, actions=None):
        self.audit_entries = []
        self.evaluations = []
        self._actions = actions or []

    def fetch_actions(self, tenant_id, capa_id):
        return self._actions

    def write_audit(self, entry):
        self.audit_entries.append(entry)

    def write_evaluation(self, evaluation):
        self.evaluations.append(evaluation)


@pytest.fixture
def client(monkeypatch):
    fake_repo = _FakeRepo(actions=[_capa_action()])
    monkeypatch.setattr(routes_mod, "get_repository", lambda: fake_repo)

    async def fake_get_context_package(capa, agent_name, repo):
        return ContextPackage(problem_summary=capa.description)

    monkeypatch.setattr(dispatch_mod, "get_context_package", fake_get_context_package)

    no_recurrence = RecurrenceResult(recurrence_detected=False, prior_occurrence_count=0)

    async def fake_run(agent_input, repo):
        return _evaluation(), no_recurrence

    monkeypatch.setattr(dispatch_mod.evaluator, "run", fake_run)

    with TestClient(app) as c:
        c._fake_repo = fake_repo
        yield c


def _capa_payload(**overrides):
    base = dict(
        tenant_id="TENANT_ACERTECH",
        capa_id="CAPA_ROUTE_TEST",
        title="Test",
        description="Test description",
        source_module="Incident",
    )
    base.update(overrides)
    return base


def test_evaluate_by_action_id_persists_and_writes_audit(client):
    resp = client.post("/capa/evaluate", json=_capa_payload(action_id="ACT_001"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == 100
    assert body["weakness_level"] == "None"
    assert len(client._fake_repo.evaluations) == 1
    assert client._fake_repo.evaluations[0].action_id == "ACT_001"
    assert len(client._fake_repo.audit_entries) == 1
    assert client._fake_repo.audit_entries[0].agent == "evaluator"


def test_evaluate_ad_hoc_text_does_not_persist(client):
    resp = client.post("/capa/evaluate", json=_capa_payload(actions=["Train the team."]))
    assert resp.status_code == 200
    assert len(client._fake_repo.evaluations) == 0
    assert len(client._fake_repo.audit_entries) == 1


def test_evaluate_unknown_action_id_returns_404(client):
    resp = client.post("/capa/evaluate", json=_capa_payload(action_id="ACT_DOES_NOT_EXIST"))
    assert resp.status_code == 404


def test_evaluate_requires_action_id_or_actions(client):
    resp = client.post("/capa/evaluate", json=_capa_payload())
    assert resp.status_code == 422


def test_evaluate_returns_502_on_evaluator_failure(client, monkeypatch):
    async def failing_run(agent_input, repo):
        raise ValueError("Evaluator failed after 2 attempts: boom")

    monkeypatch.setattr(dispatch_mod.evaluator, "run", failing_run)
    resp = client.post("/capa/evaluate", json=_capa_payload(action_id="ACT_001"))
    assert resp.status_code == 502
