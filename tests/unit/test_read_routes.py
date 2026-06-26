"""Unit tests for the Phase 7 read endpoints (GET /capa/{id}, GET /capas,
GET /capa/{id}/audit) — mocks get_repository so no DB is touched. See
phases/phase7.md decision 5."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import api.routes as routes_mod  # noqa: E402
from main import app  # noqa: E402
from models.schemas import AuditTrailEntry, Capa, CapaAction  # noqa: E402


def _capa(capa_id="CAPA_READ_TEST") -> Capa:
    return Capa.model_validate(
        dict(
            capa_id=capa_id,
            tenant_id="TENANT_ACERTECH",
            site_id="SITE_001",
            source_module="Incident",
            source_record_id="SRC_1",
            owner_group_id="GRP_1",
            capa_title="Title",
            capa_description="Description",
            priority_id="P1",
            severity_id="S1",
            capa_type_id="CT1",
            status_id="ST1",
            created_by="EMP_001",
            due_date="2026-12-01",
        )
    )


def _action() -> CapaAction:
    return CapaAction.model_validate(
        dict(
            action_id="ACT_001",
            capa_id="CAPA_READ_TEST",
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


def _audit_entry() -> AuditTrailEntry:
    return AuditTrailEntry(
        request_id="REQ_001",
        tenant_id="TENANT_ACERTECH",
        agent="evaluator",
        input_payload={"capa_id": "CAPA_READ_TEST"},
        output_payload={"score": 80},
    )


class _FakeRepo:
    def __init__(self, capa=None, actions=None, rca=None, audit_entries=None, total_capas=0):
        self._capa = capa
        self._actions = actions or []
        self._rca = rca
        self._audit_entries = audit_entries or []
        self._total_capas = total_capas

    def fetch_capa(self, tenant_id, capa_id):
        return self._capa if self._capa and self._capa.capa_id == capa_id else None

    def fetch_actions(self, tenant_id, capa_id):
        return self._actions

    def fetch_rca(self, tenant_id, capa_id):
        return self._rca

    def fetch_capas(self, tenant_id, limit, offset, site_id=None, status_id=None):
        return [self._capa] if self._capa else []

    def count_capas(self, tenant_id, site_id=None, status_id=None):
        return self._total_capas

    def fetch_audit_trail(self, tenant_id, capa_id=None, agent=None, limit=50, offset=0):
        return self._audit_entries

    def count_audit_trail(self, tenant_id, capa_id=None, agent=None):
        return len(self._audit_entries)


@pytest.fixture
def client(monkeypatch):
    fake_repo = _FakeRepo(
        capa=_capa(), actions=[_action()], audit_entries=[_audit_entry()], total_capas=1
    )
    monkeypatch.setattr(routes_mod, "get_repository", lambda: fake_repo)
    with TestClient(app) as c:
        yield c


def test_get_capa_found(client):
    resp = client.get("/capa/CAPA_READ_TEST", params={"tenant_id": "TENANT_ACERTECH"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["capa"]["capa_id"] == "CAPA_READ_TEST"
    assert len(body["actions"]) == 1
    assert body["rca"] is None


def test_get_capa_not_found(client):
    resp = client.get("/capa/CAPA_DOES_NOT_EXIST", params={"tenant_id": "TENANT_ACERTECH"})
    assert resp.status_code == 404


def test_get_capa_requires_tenant_id(client):
    resp = client.get("/capa/CAPA_READ_TEST")
    assert resp.status_code == 422


def test_list_capas_returns_total_and_items(client):
    resp = client.get("/capas", params={"tenant_id": "TENANT_ACERTECH"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["limit"] == 50
    assert body["offset"] == 0


def test_list_capas_rejects_limit_over_max(client):
    resp = client.get("/capas", params={"tenant_id": "TENANT_ACERTECH", "limit": 9999})
    assert resp.status_code == 422


def test_get_capa_audit_trail(client):
    resp = client.get(
        "/capa/CAPA_READ_TEST/audit", params={"tenant_id": "TENANT_ACERTECH"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["agent"] == "evaluator"
