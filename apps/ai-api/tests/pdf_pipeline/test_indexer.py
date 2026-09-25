import csv

import pytest
from qdrant_client import QdrantClient

from ai_api.rag import indexer

VOCAB = ["cloud", "office", "travel", "legal", "meal"]


def fake_embed(texts):
    return [[float(t.lower().count(w)) for w in VOCAB] for t in texts]


def _write_coa(path):
    rows = [
        {"account_code": "6010", "account_name": "Cloud Hosting", "level_2": "Technology", "level_3": "Cloud Infrastructure", "description": "cloud servers and hosting"},
        {"account_code": "6500", "account_name": "Office Supplies", "level_2": "Facilities & Office", "level_3": "Office Supplies", "description": "office stationery"},
        {"account_code": "7000", "account_name": "Travel", "level_2": "Travel & Entertainment", "level_3": "Airfare", "description": "travel and flights"},
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account_code", "account_name", "level_2", "level_3", "description"])
        w.writeheader()
        w.writerows(rows)


@pytest.fixture
def memory_client(monkeypatch):
    """Swap the module-global Qdrant client for an in-memory instance."""
    client = QdrantClient(location=":memory:")
    monkeypatch.setattr(indexer, "_client", client)
    return client


def test_build_index_populates_collection(tmp_path, memory_client):
    coa = tmp_path / "coa.csv"
    _write_coa(coa)
    indexer.build_index(csv_path=str(coa), tenant_id="acme", embed_fn=fake_embed)
    coll = indexer._collection_name("acme")
    assert memory_client.count(coll).count == 3


def test_retrieve_accounts_returns_most_relevant_first(tmp_path, memory_client):
    coa = tmp_path / "coa.csv"
    _write_coa(coa)
    indexer.build_index(csv_path=str(coa), tenant_id="acme", embed_fn=fake_embed)

    results = indexer.retrieve_accounts(
        "cloud hosting for servers", top_k=2, tenant_id="acme", embed_fn=fake_embed
    )
    assert results[0]["account_code"] == "6010"
    assert len(results) == 2
    assert results[0]["level_2"] == "Technology"
    assert results[0]["level_3"] == "Cloud Infrastructure"


def test_retrieve_is_tenant_scoped(tmp_path, memory_client):
    coa = tmp_path / "coa.csv"
    _write_coa(coa)
    indexer.build_index(csv_path=str(coa), tenant_id="acme", embed_fn=fake_embed)

    assert indexer.retrieve_accounts("cloud", tenant_id="other", embed_fn=fake_embed) == []


def test_build_index_skips_empty_chart(tmp_path, memory_client):
    coa = tmp_path / "empty.csv"
    with open(coa, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account_code", "account_name", "level_2", "level_3", "description"])
        w.writeheader()
    indexer.build_index(csv_path=str(coa), tenant_id="acme", embed_fn=fake_embed)
    assert indexer.retrieve_accounts("anything", tenant_id="acme", embed_fn=fake_embed) == []


def test_build_index_is_idempotent(tmp_path, memory_client):
    coa = tmp_path / "coa.csv"
    _write_coa(coa)

    calls = {"n": 0}

    def counting_embed(texts):
        calls["n"] += 1
        return fake_embed(texts)

    indexer.build_index(csv_path=str(coa), tenant_id="acme", embed_fn=counting_embed)
    indexer.build_index(csv_path=str(coa), tenant_id="acme", embed_fn=counting_embed)
    assert calls["n"] == 1
