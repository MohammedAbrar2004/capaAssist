"""1b.3 — Vector store seeder.

Populates three ChromaDB collections from the mirrored Postgres schema +
static SOP/regulatory text files (copied into `service/data/` so `service/`
has no seed-time dependency on `reference/`):

  historical_capas     — one document per CAPA_ACTIONS row (SQL join across
                          CAPA / CAPA_RCA / CAPA_REVIEWS, root cause + action
                          text + derived effectiveness)
  sop_documents         — one document per SOP .txt file (whole file)
  regulatory_documents  — one document per regulatory .txt file (whole file)

Two-phase RAM strategy per collection: embed first with fastembed then
release the model, then open ChromaDB and insert the pre-computed
embeddings — the model and the HNSW index are never in RAM simultaneously.

Run one collection at a time (recommended on constrained RAM):
    conda activate capa-ai
    cd service
    python seeds/seed_vector_db.py --collection historical_capas
    python seeds/seed_vector_db.py --collection sop_documents
    python seeds/seed_vector_db.py --collection regulatory_documents
    python seeds/seed_vector_db.py --smoke-test

Or seed everything in one process: `python seeds/seed_vector_db.py --collection all`
"""

import argparse
import gc
import os
import sys
from pathlib import Path

import chromadb
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

EMBED_BATCH = 4
INSERT_BATCH = 50


def ram() -> str:
    proc = psutil.Process(os.getpid())
    used = proc.memory_info().rss / 1024 / 1024
    pct = psutil.virtual_memory().percent
    return f"{used:.0f}MB process | {pct:.0f}% system"


def compute_embeddings(documents: list[str]) -> list[list[float]]:
    print(f"  Loading fastembed model {config.EMBEDDING_MODEL_NAME} | RAM: {ram()}")
    from fastembed import TextEmbedding
    model = TextEmbedding(config.EMBEDDING_MODEL_NAME)
    embeddings = [e.tolist() for e in model.embed(documents, batch_size=EMBED_BATCH)]
    del model
    gc.collect()
    print(f"  Model unloaded | RAM: {ram()}")
    return embeddings


def get_chroma_client() -> chromadb.PersistentClient:
    os.makedirs(config.CHROMA_PATH, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.CHROMA_PATH))


def _upsert_batched(collection, documents, embeddings, metadatas, ids) -> None:
    total = len(ids)
    for i in range(0, total, INSERT_BATCH):
        sl = slice(i, i + INSERT_BATCH)
        collection.upsert(
            documents=documents[sl],
            embeddings=embeddings[sl],
            metadatas=metadatas[sl],
            ids=ids[sl],
        )
        print(f"    inserted {min(i + INSERT_BATCH, total)}/{total} | RAM: {ram()}")


# --- Collection 1: historical_capas ----------------------------------------

def seed_historical_capas(client: chromadb.PersistentClient) -> int:
    print(f"  RAM at entry: {ram()}")

    import psycopg2
    import psycopg2.extras

    # CAPA_REVIEWS only FKs to CAPA_ID (no ACTION_ID column in the real schema),
    # so it can't be joined per-action without fanning out across a CAPA's
    # other actions/reviews. Per-action effectiveness instead comes from
    # CAPA_ACTIONS.VERIFIED_BY/VERIFIED_DATE, which are action-scoped.
    sql = """
        SELECT
            a.ACTION_ID, a.ACTION_TITLE, a.ACTION_DESCRIPTION, a.CAPA_TYPE_ID,
            a.VERIFIED_BY, a.VERIFIED_DATE,
            c.CAPA_ID, c.CAPA_TITLE, c.CAPA_DESCRIPTION, c.SOURCE_MODULE,
            c.SEVERITY_ID, sm.SEVERITY_NAME, st.STATUS AS capa_status,
            ms.SITE_NAME, c.ROOT_CAUSE,
            rca.ROOT_CAUSE_CATEGORY, cat.CATEGORY_NAME
        FROM CAPA_ACTIONS a
        JOIN CAPA c ON a.CAPA_ID = c.CAPA_ID
        JOIN MSTR_SEVERITY_MASTER sm ON c.SEVERITY_ID = sm.SEVERITY_ID
        JOIN CAPA_STATUS_MASTER st ON c.STATUS_ID = st.STATUS_ID
        JOIN MSTR_TENANT_SITES ms ON c.SITE_ID = ms.SITE_ID
        LEFT JOIN CAPA_RCA rca ON c.CAPA_ID = rca.CAPA_ID
        LEFT JOIN CAPA_CATEGORIES cat ON rca.ROOT_CAUSE_CATEGORY = cat.CATEGORY_ID
        WHERE c.TENANT_ID = %s
        ORDER BY a.ACTION_ID
    """

    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (config.CAPA_TENANT_ID,))
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        print("  [historical_capas] No rows — run seeds/load_seed.py first.")
        return 0

    documents, metadatas, ids = [], [], []
    for r in rows:
        doc = (
            f"CAPA: {r['capa_title']}. "
            f"Description: {r['capa_description'] or ''}. "
            f"Root cause: {r['root_cause'] or 'Not recorded'}. "
            f"Root cause category: {r['category_name'] or 'Unknown'}. "
            f"Action ({r['capa_type_id']}): {r['action_title'] or ''}. "
            f"{r['action_description'] or ''}."
        )
        meta = {
            "action_id": r["action_id"],
            "capa_id": r["capa_id"],
            "capa_title": r["capa_title"] or "",
            "source_module": r["source_module"] or "",
            "severity": r["severity_name"] or "",
            "capa_status": r["capa_status"] or "",
            "site": r["site_name"] or "",
            "root_cause_category": r["category_name"] or "",
            "action_type": r["capa_type_id"] or "",
            "action_title": r["action_title"] or "",
            "verified": bool(r["verified_by"]),
        }
        documents.append(doc)
        metadatas.append(meta)
        ids.append(f"action-{r['action_id']}")

    print(f"  {len(documents)} documents prepared | RAM: {ram()}")
    embeddings = compute_embeddings(documents)

    collection = client.get_or_create_collection(
        name="historical_capas",
        embedding_function=config.EMBEDDING_FN,
        metadata={"hnsw:space": "cosine"},
    )
    _upsert_batched(collection, documents, embeddings, metadatas, ids)
    del documents, embeddings, metadatas, ids
    gc.collect()

    count = collection.count()
    print(f"  [historical_capas] {count} documents stored | RAM: {ram()}")
    return count


# --- Collections 2 & 3: SOP / regulatory text files -------------------------

def _parse_sop_header(text: str) -> dict:
    meta = {"source_type": "sop"}
    for line in text.splitlines()[:10]:
        if line.startswith("SOP ID:"):
            meta["doc_id"] = line.split(":", 1)[1].strip()
        elif line.startswith("Title:"):
            meta["title"] = line.split(":", 1)[1].strip()
        elif line.startswith("Version:"):
            meta["version"] = line.split(":", 1)[1].strip()
        elif line.startswith("Applicable Sites:"):
            meta["applicable_sites"] = line.split(":", 1)[1].strip()
    return meta


def _parse_reg_header(text: str) -> dict:
    meta = {"source_type": "regulatory"}
    for line in text.splitlines()[:8]:
        if line.startswith("REGULATORY REFERENCE:"):
            meta["doc_id"] = line.split(":", 1)[1].strip()
        elif line.startswith("Standard:"):
            meta["standard"] = line.split(":", 1)[1].strip()
        elif line.startswith("Clause:") or line.startswith("Title:"):
            key = "clause" if line.startswith("Clause:") else "title"
            meta[key] = line.split(":", 1)[1].strip()
        elif line.startswith("Issuing Body:"):
            meta["issuing_body"] = line.split(":", 1)[1].strip()
    return meta


def _seed_text_dir(client, collection_name: str, directory: Path, parse_header) -> int:
    print(f"  RAM at entry: {ram()}")
    if not directory.exists():
        print(f"  [{collection_name}] Directory not found: {directory}")
        return 0
    files = sorted(directory.glob("*.txt"))
    if not files:
        print(f"  [{collection_name}] No .txt files in {directory}")
        return 0

    documents, metadatas, ids = [], [], []
    for fpath in files:
        text = fpath.read_text(encoding="utf-8")
        meta = parse_header(text)
        meta["filename"] = fpath.name
        documents.append(text)
        metadatas.append(meta)
        ids.append(fpath.stem)

    print(f"  {len(documents)} files loaded | RAM: {ram()}")
    embeddings = compute_embeddings(documents)

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=config.EMBEDDING_FN,
        metadata={"hnsw:space": "cosine"},
    )
    _upsert_batched(collection, documents, embeddings, metadatas, ids)
    del documents, embeddings, metadatas, ids
    gc.collect()

    count = collection.count()
    print(f"  [{collection_name}] {count} documents stored | RAM: {ram()}")
    return count


def seed_sop_documents(client) -> int:
    return _seed_text_dir(client, "sop_documents", config.SOPS_DIR, _parse_sop_header)


def seed_regulatory_documents(client) -> int:
    return _seed_text_dir(client, "regulatory_documents", config.REGULATORY_DIR, _parse_reg_header)


# --- Smoke test --------------------------------------------------------------

def smoke_test() -> None:
    client = get_chroma_client()
    queries = {
        "historical_capas": "wire rope failure on overhead crane recurring",
        "sop_documents": "lockout tagout procedure",
        "regulatory_documents": "ISO 45001 management review",
    }
    for name, query in queries.items():
        try:
            collection = client.get_collection(name=name, embedding_function=config.EMBEDDING_FN)
        except Exception as exc:
            print(f"[{name}] collection missing: {exc}")
            continue
        result = collection.query(query_texts=[query], n_results=5)
        ids = result.get("ids", [[]])[0]
        print(f"[{name}] count={collection.count()} top-5 for {query!r}: {ids}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", choices=["historical_capas", "sop_documents", "regulatory_documents", "all"])
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()

    if args.smoke_test:
        smoke_test()
        return

    if not args.collection:
        parser.error("--collection or --smoke-test is required")

    client = get_chroma_client()
    if args.collection in ("historical_capas", "all"):
        seed_historical_capas(client)
    if args.collection in ("sop_documents", "all"):
        seed_sop_documents(client)
    if args.collection in ("regulatory_documents", "all"):
        seed_regulatory_documents(client)


if __name__ == "__main__":
    main()
