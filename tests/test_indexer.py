import csv

from spend_predictor.rag import indexer

VOCAB = ["cloud", "office", "travel", "legal", "meal"]


def fake_embed(texts):
    return [[float(t.lower().count(w)) for w in VOCAB] for t in texts]


def _write_coa(path):
    rows = [
        {"account_code": "6010", "account_name": "Cloud Hosting", "description": "cloud servers and hosting", "category": "IT"},
        {"account_code": "6500", "account_name": "Office Supplies", "description": "office stationery", "category": "Admin"},
        {"account_code": "7000", "account_name": "Travel", "description": "travel and flights", "category": "Ops"},
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account_code", "account_name", "description", "category"])
        w.writeheader()
        w.writerows(rows)


def test_build_index_populates_collection(tmp_path):
    coa = tmp_path / "coa.csv"
    _write_coa(coa)
    coll = indexer.build_index(csv_path=str(coa), chroma_dir=str(tmp_path / "db"), embed_fn=fake_embed)
    assert coll.count() == 3


def test_retrieve_accounts_returns_most_relevant_first(tmp_path):
    coa = tmp_path / "coa.csv"
    _write_coa(coa)
    db = str(tmp_path / "db")
    indexer.build_index(csv_path=str(coa), chroma_dir=db, embed_fn=fake_embed)

    results = indexer.retrieve_accounts(
        "cloud hosting for servers", top_k=2, embed_fn=fake_embed, chroma_dir=db
    )
    assert results[0]["account_code"] == "6010"
    assert len(results) == 2


def test_build_index_skips_empty_chart(tmp_path):
    coa = tmp_path / "empty.csv"
    with open(coa, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account_code", "account_name", "description", "category"])
        w.writeheader()
    coll = indexer.build_index(csv_path=str(coa), chroma_dir=str(tmp_path / "db"), embed_fn=fake_embed)
    assert coll.count() == 0  # no crash on empty chart


def test_build_index_is_idempotent(tmp_path):
    coa = tmp_path / "coa.csv"
    _write_coa(coa)

    calls = {"n": 0}

    def counting_embed(texts):
        calls["n"] += 1
        return fake_embed(texts)

    db = str(tmp_path / "db")
    indexer.build_index(csv_path=str(coa), chroma_dir=db, embed_fn=counting_embed)
    indexer.build_index(csv_path=str(coa), chroma_dir=db, embed_fn=counting_embed)
    assert calls["n"] == 1  # second build is a no-op
