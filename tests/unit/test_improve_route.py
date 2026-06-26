"""Unit test for POST /capa/improve's plumbing (cache hit/miss, audit write,
404/422/502) — mocks evaluator.run/improver.run/get_repository/
get_context_package so no network or DB is touched. See phases/phase5.md."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import api.routes as routes_mod  # noqa: E402
import orchestrator.dispatch as dispatch_mod  # noqa: E402
import services.eval_cache as eval_cache  # noqa: E402
from main import app  # noqa: E402
from models.schemas import (  # noqa: E402
    CapaAction,
    ContextPackage,
    DimensionResult,
    EvaluationResult,
    ImproverResult,
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
            capa_id="CAPA_IMPROVE_ROUTE_TEST",
            tenant_id="TENANT_ACERTECH",
            site_id="SITE_001",
            action_title="Train the team",
            action_description="Train the team on the SOP.",
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
        self._actions = actions or []

    def fetch_actions(self, tenant_id, capa_id):
        return self._actions

    def write_audit(self, entry):
        self.audit_entries.append(entry)


@pytest.fixture(autouse=True)
def _clear_cache():
    eval_cache._cache.clear()
    yield
    eval_cache._cache.clear()


@pytest.fixture
def client(monkeypatch):
    fake_repo = _FakeRepo(actions=[_capa_action()])
    monkeypatch.setattr(routes_mod, "get_repository", lambda: fake_repo)

    async def fake_get_context_package(capa, agent_name, repo):
        return ContextPackage(problem_summary=capa.description)

    monkeypatch.setattr(dispatch_mod, "get_context_package", fake_get_context_package)

    no_recurrence = RecurrenceResult(recurrence_detected=False, prior_occurrence_count=0)
    state = {"evaluator_calls": 0}

    async def fake_evaluator_run(agent_input, repo):
        state["evaluator_calls"] += 1
        return _evaluation(), no_recurrence

    async def fake_improver_run(agent_input, eval_result, recurrence):
        return ImproverResult(
            original_action_text=agent_input.action_text,
            improved_action_title="Improved title",
            improved_action_description="Improved description.",
            changes_explained=["Added an owner."],
        )

    monkeypatch.setattr(dispatch_mod.evaluator, "run", fake_evaluator_run)
    monkeypatch.setattr(dispatch_mod.improver, "run", fake_improver_run)

    with TestClient(app) as c:
        c._fake_repo = fake_repo
        c._test_state = state
        yield c


def _capa_payload(**overrides):
    base = dict(
        tenant_id="TENANT_ACERTECH",
        capa_id="CAPA_IMPROVE_ROUTE_TEST",
        title="Test",
        description="Test description",
        source_module="Incident",
    )
    base.update(overrides)
    return base


def test_improve_cache_miss_runs_evaluator_and_populates_cache(client):
    resp = client.post("/capa/improve", json=_capa_payload(action_id="ACT_001"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["improved_action_title"] == "Improved title"
    assert body["changes_explained"] == ["Added an owner."]
    assert client._test_state["evaluator_calls"] == 1
    assert len(client._fake_repo.audit_entries) == 1
    assert client._fake_repo.audit_entries[0].agent == "improver"

    key = eval_cache.make_key("TENANT_ACERTECH", "CAPA_IMPROVE_ROUTE_TEST", "ACT_001", "")
    assert eval_cache.get(key) is not None


def test_improve_cache_hit_skips_evaluator(client):
    key = eval_cache.make_key(
        "TENANT_ACERTECH", "CAPA_IMPROVE_ROUTE_TEST", "ACT_001",
        "Train the team: Train the team on the SOP.",
    )
    no_recurrence = RecurrenceResult(recurrence_detected=False, prior_occurrence_count=0)
    eval_cache.put(key, (_evaluation(), no_recurrence))

    resp = client.post("/capa/improve", json=_capa_payload(action_id="ACT_001"))
    assert resp.status_code == 200
    assert client._test_state["evaluator_calls"] == 0


def test_improve_unknown_action_id_returns_404(client):
    resp = client.post("/capa/improve", json=_capa_payload(action_id="ACT_DOES_NOT_EXIST"))
    assert resp.status_code == 404


def test_improve_requires_action_id_or_actions(client):
    resp = client.post("/capa/improve", json=_capa_payload())
    assert resp.status_code == 422


def test_improve_returns_502_on_agent_failure(client, monkeypatch):
    async def failing_run(agent_input, eval_result, recurrence):
        raise ValueError("Improver failed: boom")

    monkeypatch.setattr(dispatch_mod.improver, "run", failing_run)
    resp = client.post("/capa/improve", json=_capa_payload(action_id="ACT_001"))
    assert resp.status_code == 502


def test_improve_ad_hoc_text_works(client):
    resp = client.post("/capa/improve", json=_capa_payload(actions=["Train the team."]))
    assert resp.status_code == 200
    assert len(client._fake_repo.audit_entries) == 1
