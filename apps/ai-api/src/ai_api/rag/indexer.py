"""Qdrant vector index over a spend taxonomy."""
from __future__ import annotations

import csv
from typing import Callable

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams
from sentence_transformers import SentenceTransformer

from .. import config

_COLLECTION_PREFIX = "spend_tree_"

_client: QdrantClient | None = None
_model: SentenceTransformer | None = None


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
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model.encode(texts, normalize_embeddings=True).tolist()


def _collection_name(tenant_id: str) -> str:
    return f"{_COLLECTION_PREFIX}{tenant_id}"


def load_accounts(csv_path: str | None = None) -> list[dict]:
    """Return the chart of accounts as a list of row dicts."""
    csv_path = csv_path or config.CHART_OF_ACCOUNTS_PATH
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def _collection_exists(client: QdrantClient, name: str) -> bool:
    collections = client.get_collections().collections
    return any(c.name == name for c in collections)


def _recreate_collection(client: QdrantClient, name: str, vector_size: int) -> None:
    """Drop ``name`` if it exists and create it empty for ``vector_size`` vectors."""
    if _collection_exists(client, name):
        client.delete_collection(name)
    client.create_collection(
        name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def build_index(
    csv_path: str | None = None,
    tenant_id: str | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] = _default_embed,
):
    """Embed the chart of accounts into a Qdrant collection for the given tenant."""
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

    has_level_3 = "level_3" in rows[0] and rows[0]["level_3"]
    documents = [
        f'{r["level_2"]} > {r["level_3"]} > {r["account_name"]}: {r["description"]}'
        if has_level_3
        else f'{r["level_2"]} > {r["account_name"]}: {r["description"]}'
        for r in rows
    ]
    metadatas = [{**r, "tenant_id": tid} for r in rows]
    embeddings = embed_fn(documents)
    vector_size = len(embeddings[0])

    _recreate_collection(client, coll, vector_size)
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
    """Return the top-K chart-of-accounts rows most relevant to the query."""
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


_TREE_COLLECTION_PREFIX = "spend_categories_"


def _tree_collection_name(tree_id: str) -> str:
    return f"{_TREE_COLLECTION_PREFIX}{tree_id}"


def _node_document(node) -> str:
    """The text embedded for a node: its path, then its own description."""
    path = " > ".join(
        value for value in (node.level_1, node.level_2, node.level_3, node.level_4)
        if value
    )
    return f"{path}: {node.description}" if node.description else path


def build_tree_index(
    nodes: list,
    tree_id: str,
    embed_fn: Callable[[list[str]], list[list[float]]] = _default_embed,
) -> None:
    """Embed a spend tree's nodes into a collection of their own."""
    if not nodes:
        return

    client = _get_client()
    coll = _tree_collection_name(tree_id)

    if _collection_exists(client, coll) and client.count(coll).count == len(nodes):
        return

    documents = [_node_document(node) for node in nodes]
    payloads = [
        {
            "spend_category_id": node.id,
            "spend_tree_id": tree_id,
            "name": node.name,
            "code": node.code,
            "depth": node.depth,
            "description": node.description,
            "level_1": node.level_1,
            "level_2": node.level_2,
            "level_3": node.level_3,
            "level_4": node.level_4,
        }
        for node in nodes
    ]
    embeddings = embed_fn(documents)

    _recreate_collection(client, coll, len(embeddings[0]))
    client.upsert(
        coll,
        points=[
            models.PointStruct(id=index, vector=emb, payload=payload)
            for index, (emb, payload) in enumerate(zip(embeddings, payloads))
        ],
    )


def retrieve_categories(
    query: str,
    tree_id: str,
    top_k: int = 5,
    embed_fn: Callable[[list[str]], list[list[float]]] = _default_embed,
) -> list[dict]:
    """The top-K nodes of one tree most relevant to a query, best first."""
    client = _get_client()
    coll = _tree_collection_name(tree_id)
    if not _collection_exists(client, coll):
        return []

    results = client.query_points(
        coll,
        query=embed_fn([query])[0],
        limit=top_k,
        with_payload=True,
    ).points
    return [r.payload for r in results if r.payload]
