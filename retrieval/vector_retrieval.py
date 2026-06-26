"""Vector retrieval system — semantic search over the 3 ChromaDB collections
seeded in Phase 1 (`seeds/seed_vector_db.py`). Synchronous client calls;
context_retrieval.py runs these via asyncio.to_thread.
"""

import threading

import chromadb

import config
from models.schemas import RegulatoryExcerpt, SimilarCapaSummary, SopExcerpt

# ChromaDB's lazily-initialized client wasn't thread-safe in the reference
# build (analysis.md / phase6 finding) — lock construction so concurrent
# retrieval calls can't race on first access.
_client_lock = threading.Lock()
_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))
    return _client


def search_historical_capas(query_text: str, n_results: int = 5) -> list[SimilarCapaSummary]:
    client = _get_client()
    try:
        collection = client.get_collection(name="historical_capas", embedding_function=config.EMBEDDING_FN)
    except Exception:
        return []
    result = collection.query(query_texts=[query_text], n_results=n_results)
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    summaries = []
    for meta, dist in zip(metadatas, distances):
        score = 1.0 - dist
        if score < config.VECTOR_SIMILARITY_THRESHOLD:
            continue
        summaries.append(
            SimilarCapaSummary(
                capa_id=meta.get("capa_id", ""),
                title=meta.get("capa_title", ""),
                root_cause_summary="",  # not stored separately in this collection's metadata
                action_summary=meta.get("action_title", ""),
                action_type=meta.get("action_type", ""),
                effectiveness_result="Verified" if meta.get("verified") else "Pending",
                site_id="",  # collection metadata stores site_name, not site_id — resolved by sql_retrieval, not here
                group_id="",
                root_cause_category=meta.get("root_cause_category") or None,
                similarity_score=score,
            )
        )
    return summaries


def search_sops(query_text: str, n_results: int = 5) -> list[SopExcerpt]:
    client = _get_client()
    try:
        collection = client.get_collection(name="sop_documents", embedding_function=config.EMBEDDING_FN)
    except Exception:
        return []
    result = collection.query(query_texts=[query_text], n_results=n_results)
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    excerpts = []
    for doc_id, doc, meta, dist in zip(ids, documents, metadatas, distances):
        score = 1.0 - dist
        if score < config.VECTOR_SIMILARITY_THRESHOLD:
            continue
        excerpts.append(
            SopExcerpt(
                id=doc_id,
                title=meta.get("title", doc_id),
                excerpt=doc[:500],
                relevance_score=score,
            )
        )
    return excerpts


def search_regulatory(query_text: str, n_results: int = 5) -> list[RegulatoryExcerpt]:
    client = _get_client()
    try:
        collection = client.get_collection(name="regulatory_documents", embedding_function=config.EMBEDDING_FN)
    except Exception:
        return []
    result = collection.query(query_texts=[query_text], n_results=n_results)
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    excerpts = []
    for doc_id, doc, meta, dist in zip(ids, documents, metadatas, distances):
        score = 1.0 - dist
        if score < config.VECTOR_SIMILARITY_THRESHOLD:
            continue
        excerpts.append(
            RegulatoryExcerpt(
                id=doc_id,
                title=meta.get("title") or meta.get("standard", doc_id),
                excerpt=doc[:500],
                relevance_score=score,
            )
        )
    return excerpts
