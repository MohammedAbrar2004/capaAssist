"""Checkpoint 7 — read endpoints against the real seeded dev DB. Self-skips
if the dev DB is unreachable, matching every other integration suite. See
phases/phase7.md.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from main import app  # noqa: E402

SEEDED_CAPA_ID = "CAPA_0001"


@pytest.fixture()
def client(repo):
    with TestClient(app) as c:
        yield c


def test_get_capa_returns_seeded_record(client, tenant):
    resp = client.get(f"/capa/{SEEDED_CAPA_ID}", params={"tenant_id": tenant})
    assert resp.status_code == 200
    body = resp.json()
    assert body["capa"]["capa_id"] == SEEDED_CAPA_ID
    assert body["capa"]["tenant_id"] == tenant


def test_get_capa_unknown_id_404s(client, tenant):
    resp = client.get("/capa/CAPA_DOES_NOT_EXIST", params={"tenant_id": tenant})
    assert resp.status_code == 404


def test_list_capas_paginates(client, tenant):
    resp = client.get("/capas", params={"tenant_id": tenant, "limit": 5, "offset": 0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= len(body["items"])
    assert len(body["items"]) <= 5


def test_list_capas_filters_by_site(client, tenant):
    detail = client.get(f"/capa/{SEEDED_CAPA_ID}", params={"tenant_id": tenant}).json()
    site_id = detail["capa"]["site_id"]

    resp = client.get("/capas", params={"tenant_id": tenant, "site_id": site_id, "limit": 50})
    assert resp.status_code == 200
    body = resp.json()
    assert all(item["site_id"] == site_id for item in body["items"])
    assert any(item["capa_id"] == SEEDED_CAPA_ID for item in body["items"])


def test_audit_trail_reflects_a_live_evaluate_call(client, tenant):
    capa_id = "CAPA_AUDIT_READ_TEST"
    payload = dict(
        tenant_id=tenant,
        capa_id=capa_id,
        title="Wire rope fraying",
        description="Inspection found frayed wire rope strands.",
        source_module="Inspection",
        actions=["Train the team."],
    )
    eval_resp = client.post("/capa/evaluate", json=payload)
    assert eval_resp.status_code == 200

    audit_resp = client.get(f"/capa/{capa_id}/audit", params={"tenant_id": tenant})
    assert audit_resp.status_code == 200
    body = audit_resp.json()
    assert body["total"] >= 1
    assert any(item["agent"] == "evaluator" for item in body["items"])
