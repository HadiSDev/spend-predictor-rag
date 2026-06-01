"""Build and access the persisted ChromaDB index of the chart of accounts."""
from __future__ import annotations

import csv
from typing import Callable

import chromadb

from .. import config

COLLECTION_NAME = "chart_of_accounts"

_model: "SentenceTransformer | None" = None


def _default_embed(texts: list[str]) -> list[list[float]]:
    """Embed texts with the configured sentence-transformers model (lazy-loaded)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model.encode(texts, normalize_embeddings=True).tolist()


def get_collection(chroma_dir: str | None = None) -> chromadb.Collection:
    """Open (or create) the persisted chart-of-accounts collection."""
    client = chromadb.PersistentClient(path=chroma_dir or config.CHROMA_DIR)
    return client.get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def _read_accounts(csv_path: str) -> list[dict]:
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def load_accounts(csv_path: str | None = None) -> list[dict]:
    """Return the chart of accounts as a list of row dicts."""
    return _read_accounts(csv_path or config.CHART_OF_ACCOUNTS_PATH)


def retrieve_accounts(
    query: str,
    top_k: int = 5,
    embed_fn: Callable[[list[str]], list[list[float]]] = _default_embed,
    chroma_dir: str | None = None,
) -> list[dict]:
    """Return the top-K chart-of-accounts rows most relevant to the query,
    ordered best-first, as metadata dicts."""
    collection = get_collection(chroma_dir)
    result = collection.query(query_embeddings=embed_fn([query]), n_results=top_k)
    return (result.get("metadatas") or [[]])[0]


def build_index(
    csv_path: str | None = None,
    chroma_dir: str | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] = _default_embed,
):
    """Embed the chart of accounts into the collection. Idempotent: a no-op if the
    collection already holds exactly one row per account."""
    csv_path = csv_path or config.CHART_OF_ACCOUNTS_PATH
    rows = _read_accounts(csv_path)
    collection = get_collection(chroma_dir)

    # An empty chart has nothing to embed; upserting empty lists would raise.
    if not rows:
        return collection

    # Idempotency is count-based per spec; content changes without a row-count
    # change require manually clearing chroma_dir to force a rebuild.
    if collection.count() == len(rows):
        return collection

    ids = [r["account_code"] for r in rows]
    documents = [
        f'{r["account_name"]}: {r["description"]} (category: {r["category"]})' for r in rows
    ]
    metadatas = [dict(r) for r in rows]
    embeddings = embed_fn(documents)
    collection.upsert(
        ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas
    )
    return collection
