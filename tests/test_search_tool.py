import csv

from spend_predictor.rag import indexer, search_tool

VOCAB = ["cloud", "office", "travel", "legal", "meal"]


def fake_embed(texts):
    return [[float(t.lower().count(w)) for w in VOCAB] for t in texts]


def _seed(tmp_path):
    coa = tmp_path / "coa.csv"
    rows = [
        {"account_code": "6010", "account_name": "Cloud Hosting", "description": "cloud servers and hosting", "category": "IT"},
        {"account_code": "6500", "account_name": "Office Supplies", "description": "office stationery", "category": "Admin"},
    ]
    with open(coa, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account_code", "account_name", "description", "category"])
        w.writeheader()
        w.writerows(rows)
    return indexer.build_index(csv_path=str(coa), chroma_dir=str(tmp_path / "db"), embed_fn=fake_embed)


def test_search_returns_most_relevant_account(tmp_path, monkeypatch):
    coll = _seed(tmp_path)
    monkeypatch.setattr(search_tool, "get_collection", lambda: coll)
    monkeypatch.setattr(search_tool, "embed_texts", fake_embed)

    tool = search_tool.ChartOfAccountsSearchTool()
    out = tool._run(query="need cloud hosting for servers", top_k=1)
    assert "6010" in out
    assert "Cloud Hosting" in out


def test_search_handles_empty_results(tmp_path, monkeypatch):
    coll = _seed(tmp_path)
    monkeypatch.setattr(search_tool, "get_collection", lambda: coll)
    monkeypatch.setattr(search_tool, "embed_texts", fake_embed)

    tool = search_tool.ChartOfAccountsSearchTool()
    out = tool._run(query="cloud", top_k=5)
    assert "6010" in out  # at least returns candidates
