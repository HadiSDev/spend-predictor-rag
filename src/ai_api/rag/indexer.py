"""Qdrant-based vector index for per-tenant chart of accounts (spend trees).

Replaces the previous ChromaDB implementation. Each tenant's spend tree is stored
in a Qdrant collection named ``spend_tree_{tenant_id}`` so that retrieval is
automatically scoped — no cross-tenant leakage possible.
"""
from __future__ import annotations

import csv
from typing import Callable

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams

from .. import config

_COLLECTION_PREFIX = "spend_tree_"

_client: QdrantClient | None = None
_model: "SentenceTransformer | None" = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            host=config.QDRANT_HOST,
            port=config.QDRANT_PORT,
            prefer_grpc=False,
        )
    return _client


def _default_embed(texts: list[str]) -> list[list[float]]:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model.encode(texts, normalize_embeddings=True).tolist()


def _collection_name(tenant_id: str) -> str:
    return f"{_COLLECTION_PREFIX}{tenant_id}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_accounts(csv_path: str | None = None) -> list[dict]:
    """Return the chart of accounts as a list of row dicts."""
    csv_path = csv_path or config.CHART_OF_ACCOUNTS_PATH
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def _collection_exists(client: QdrantClient, name: str) -> bool:
    collections = client.get_collections().collections
    return any(c.name == name for c in collections)


def build_index(
    csv_path: str | None = None,
    tenant_id: str | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] = _default_embed,
):
    """Embed the chart of accounts into a Qdrant collection for the given tenant.

    Idempotent: skips if the collection already holds exactly one point per row.
    Pass ``tenant_id="default"`` or omit for the single-tenant / dev case.
    """
    csv_path = csv_path or config.CHART_OF_ACCOUNTS_PATH
    rows = load_accounts(csv_path)
    if not rows:
        return

    tid = tenant_id or "default"
    client = _get_client()
    coll = _collection_name(tid)

    if _collection_exists(client, coll):
        count = client.count(coll).count
        if count == len(rows):
            return

    # Build document strings and embeddings
    has_level_3 = "level_3" in rows[0] and rows[0]["level_3"]
    ids = [r["account_code"] for r in rows]
    documents = [
        f'{r["level_2"]} > {r["level_3"]} > {r["account_name"]}: {r["description"]}'
        if has_level_3
        else f'{r["level_2"]} > {r["account_name"]}: {r["description"]}'
        for r in rows
    ]
    metadatas = [{**r, "tenant_id": tid} for r in rows]
    embeddings = embed_fn(documents)
    vector_size = len(embeddings[0])

    # Recreate collection (idempotent: count check above means this only runs on
    # first build or after a row-count change)
    try:
        client.delete_collection(coll)
    except Exception:
        pass

    client.create_collection(
        coll,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )

    client.upsert(
        coll,
        points=[
            models.PointStruct(
                id=idx,
                vector=emb,
                payload=meta,
            )
            for idx, (emb, meta) in enumerate(zip(embeddings, metadatas))
        ],
    )


def retrieve_accounts(
    query: str,
    top_k: int = 5,
    tenant_id: str | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] = _default_embed,
) -> list[dict]:
    """Return the top-K chart-of-accounts rows most relevant to the query.

    Retrieval is scoped to the tenant's spend tree collection. Returns metadata
    dicts ordered best-first.
    """
    tid = tenant_id or "default"
    client = _get_client()
    coll = _collection_name(tid)

    if not _collection_exists(client, coll):
        return []

    query_vector = embed_fn([query])[0]
    results = client.query_points(
        coll,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    ).points

    return [r.payload for r in results if r.payload]
