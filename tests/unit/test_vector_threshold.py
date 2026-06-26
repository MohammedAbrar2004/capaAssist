"""Sub-Phase 2b — vector_retrieval's 3 search functions must drop results
below config.VECTOR_SIMILARITY_THRESHOLD. Pure unit test: fakes the Chroma
client/collection so distances are controlled exactly, no real ChromaDB.
"""

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import config  # noqa: E402
from retrieval import vector_retrieval  # noqa: E402


class _FakeCollection:
    def __init__(self, ids, documents, metadatas, distances):
        self._result = {
            "ids": [ids], "documents": [documents], "metadatas": [metadatas], "distances": [distances],
        }

    def query(self, query_texts, n_results):
        return self._result


class _FakeClient:
    def __init__(self, collection):
        self._collection = collection

    def get_collection(self, name, embedding_function=None):
        return self._collection


def test_search_historical_capas_drops_low_similarity(monkeypatch):
    # distance 0.1 -> score 0.9 (keep); distance 0.95 -> score 0.05 (drop, below 0.2 default)
    collection = _FakeCollection(
        ids=["a", "b"],
        documents=["doc a", "doc b"],
        metadatas=[{"capa_id": "CAPA_A"}, {"capa_id": "CAPA_B"}],
        distances=[0.1, 0.95],
    )
    monkeypatch.setattr(vector_retrieval, "_get_client", lambda: _FakeClient(collection))

    results = vector_retrieval.search_historical_capas("query")

    assert len(results) == 1
    assert results[0].capa_id == "CAPA_A"
    assert results[0].similarity_score >= config.VECTOR_SIMILARITY_THRESHOLD


def test_search_sops_drops_low_similarity(monkeypatch):
    collection = _FakeCollection(
        ids=["SOP-1", "SOP-2"],
        documents=["relevant sop text", "irrelevant sop text"],
        metadatas=[{"title": "Relevant"}, {"title": "Irrelevant"}],
        distances=[0.05, 0.99],
    )
    monkeypatch.setattr(vector_retrieval, "_get_client", lambda: _FakeClient(collection))

    results = vector_retrieval.search_sops("query")

    assert len(results) == 1
    assert results[0].id == "SOP-1"


def test_search_regulatory_drops_low_similarity(monkeypatch):
    collection = _FakeCollection(
        ids=["REG-1", "REG-2"],
        documents=["relevant reg text", "irrelevant reg text"],
        metadatas=[{"title": "Relevant"}, {"title": "Irrelevant"}],
        distances=[0.0, 1.5],  # distance > 1 -> negative score, must be dropped
    )
    monkeypatch.setattr(vector_retrieval, "_get_client", lambda: _FakeClient(collection))

    results = vector_retrieval.search_regulatory("query")

    assert len(results) == 1
    assert results[0].id == "REG-1"


def test_search_returns_empty_list_when_nothing_clears_threshold(monkeypatch):
    collection = _FakeCollection(
        ids=["a"], documents=["doc"], metadatas=[{"capa_id": "CAPA_A"}], distances=[0.99],
    )
    monkeypatch.setattr(vector_retrieval, "_get_client", lambda: _FakeClient(collection))

    assert vector_retrieval.search_historical_capas("query") == []
