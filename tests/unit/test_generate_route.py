"""Unit test for POST /capa/generate's plumbing (route shape, audit write,
error handling) — mocks generator.run/get_repository/get_context_package so
no network or DB is touched. The agent logic itself is covered by
tests/unit/test_generator.py and tests/integration/test_generator.py."""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import api.routes as routes_mod  # noqa: E402
import orchestrator.dispatch as dispatch_mod  # noqa: E402
from main import app  # noqa: E402
from models.schemas import ContextPackage, GeneratedAction  # noqa: E402


def _generated_action() -> GeneratedAction:
    return GeneratedAction.model_validate(
        dict(
            type="Corrective",
            title="Replace failed wire rope",
            requirements=[{"label": "x", "mandatory": True, "options": [{"text": "y"}]}],
            recommended_owner_role="Maintenance Supervisor",
            recommended_due_date=(date.today() + timedelta(days=45)).isoformat(),
            required_evidence=["a", "b"],
            effectiveness_check_method="Re-inspection",
            rationale="r",
            linked_root_cause="root cause",
            confidence_level="High",
        )
    )


class _FakeRepo:
    def __init__(self):
        self.audit_entries = []

    def write_audit(self, entry):
        self.audit_entries.append(entry)


@pytest.fixture
def client(monkeypatch):
    fake_repo = _FakeRepo()
    monkeypatch.setattr(routes_mod, "get_repository", lambda: fake_repo)

    async def fake_get_context_package(capa, agent_name, repo):
        return ContextPackage(problem_summary=capa.description)

    monkeypatch.setattr(dispatch_mod, "get_context_package", fake_get_context_package)

    async def fake_run(agent_input, repo, num_actions=2):
        return [_generated_action() for _ in range(num_actions)]

    monkeypatch.setattr(dispatch_mod.generator, "run", fake_run)

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
        requested_action_type="Corrective",
    )
    base.update(overrides)
    return base


def test_generate_returns_actions_and_writes_audit(client):
    resp = client.post("/capa/generate", json=_capa_payload(num_actions=2))
    assert resp.status_code == 200
    body = resp.json()
    assert body["action_type"] == "Corrective"
    assert len(body["actions"]) == 2
    assert len(client._fake_repo.audit_entries) == 1
    assert client._fake_repo.audit_entries[0].agent == "generator"


def test_generate_requires_action_type(client):
    resp = client.post("/capa/generate", json=_capa_payload(requested_action_type=None))
    assert resp.status_code == 422


def test_generate_returns_502_on_generator_failure(client, monkeypatch):
    async def failing_run(agent_input, repo, num_actions=2):
        raise ValueError("Generator failed after 2 attempts: boom")

    monkeypatch.setattr(dispatch_mod.generator, "run", failing_run)
    resp = client.post("/capa/generate", json=_capa_payload())
    assert resp.status_code == 502
