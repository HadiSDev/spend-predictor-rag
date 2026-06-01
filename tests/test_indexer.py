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
