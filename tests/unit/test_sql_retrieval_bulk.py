"""Sub-Phase 2b — confirm the N+1 fix actually fixed the N+1: fetch_similar_capas
and fetch_effective_actions must call the bulk repository methods exactly
once each, never the per-row fetch_actions/fetch_rca/fetch_capa, regardless
of how many candidates come back. Pure unit test against a fake repository —
no DB, no network.
"""

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from models.schemas import Capa, CapaAction, CapaRCA, CapaType  # noqa: E402
from retrieval import sql_retrieval  # noqa: E402


def _capa(capa_id: str) -> Capa:
    return Capa(
        capa_id=capa_id, tenant_id="T", site_id="SITE_01", source_module="Incident",
        source_record_id="X", owner_group_id="GROUP_01", capa_title=f"title {capa_id}",
        capa_description="d", priority_id="PRI_LOW", severity_id="SEV_LOW",
        capa_type_id="TYPE_CORRECTIVE", status_id="STATUS_OPEN", created_by="x@x.com",
        due_date="2026-01-01",
    )


def _action(capa_id: str, action_id: str) -> CapaAction:
    return CapaAction(
        action_id=action_id, capa_id=capa_id, tenant_id="T", site_id="SITE_01",
        action_title="t", action_description="d", priority_id="PRI_LOW",
        capa_type_id="TYPE_CORRECTIVE", severity_id="SEV_LOW", assigned_to="x@x.com",
        status_id="STATUS_OPEN", due_date="2026-01-01",
    )


class _CountingFakeRepo:
    """Duck-typed stand-in for CapaRepository — counts calls to the per-row
    methods (must stay at 0) vs. the bulk methods (must stay at 1)."""

    def __init__(self, capa_ids: list[str]):
        self.capa_ids = capa_ids
        self.calls = {"fetch_actions": 0, "fetch_rca": 0, "fetch_capa": 0,
                      "fetch_actions_bulk": 0, "fetch_rca_bulk": 0, "fetch_capas_bulk": 0}

    def fetch_similar_capas(self, tenant_id, site_id=None, category_id=None, limit=10):
        return [_capa(cid) for cid in self.capa_ids]

    def fetch_effective_actions(self, tenant_id):
        return [_action(cid, f"ACT_{cid}") for cid in self.capa_ids]

    def fetch_actions(self, tenant_id, capa_id):
        self.calls["fetch_actions"] += 1
        return [_action(capa_id, f"ACT_{capa_id}")]

    def fetch_actions_bulk(self, tenant_id, capa_ids):
        self.calls["fetch_actions_bulk"] += 1
        return {cid: [_action(cid, f"ACT_{cid}")] for cid in capa_ids}

    def fetch_rca(self, tenant_id, capa_id):
        self.calls["fetch_rca"] += 1
        return None

    def fetch_rca_bulk(self, tenant_id, capa_ids):
        self.calls["fetch_rca_bulk"] += 1
        return {}

    def fetch_capa(self, tenant_id, capa_id):
        self.calls["fetch_capa"] += 1
        return _capa(capa_id)

    def fetch_capas_bulk(self, tenant_id, capa_ids):
        self.calls["fetch_capas_bulk"] += 1
        return {cid: _capa(cid) for cid in capa_ids}

    def fetch_capa_type(self, capa_type_id):
        return CapaType(capa_type_id="TYPE_CORRECTIVE", capa_type_name="Corrective")


def test_fetch_similar_capas_uses_bulk_not_per_row():
    capa_ids = [f"CAPA_{i:04d}" for i in range(15)]
    repo = _CountingFakeRepo(capa_ids)

    sql_retrieval.fetch_similar_capas(repo, "T", site_id="SITE_01")

    assert repo.calls["fetch_actions_bulk"] == 1
    assert repo.calls["fetch_rca_bulk"] == 1
    assert repo.calls["fetch_actions"] == 0
    assert repo.calls["fetch_rca"] == 0


def test_fetch_effective_actions_uses_bulk_not_per_row():
    capa_ids = [f"CAPA_{i:04d}" for i in range(25)]
    repo = _CountingFakeRepo(capa_ids)

    sql_retrieval.fetch_effective_actions(repo, "T", limit=20)

    assert repo.calls["fetch_capas_bulk"] == 1
    assert repo.calls["fetch_rca_bulk"] == 1
    assert repo.calls["fetch_capa"] == 0
    assert repo.calls["fetch_rca"] == 0


def test_structural_match_scores_higher_than_fallback():
    repo = _CountingFakeRepo(["CAPA_0001"])
    structural, is_fallback = sql_retrieval.fetch_similar_capas(repo, "T", site_id="SITE_01")
    fallback, is_fallback2 = sql_retrieval.fetch_similar_capas(repo, "T")

    assert is_fallback is False
    assert is_fallback2 is True
    assert structural[0].similarity_score > fallback[0].similarity_score
