from pathlib import Path

from spend_predictor.synthdata.templategen import search


def test_presets_are_nonempty_query_strings():
    assert search.PRESETS  # at least one preset
    assert all(isinstance(q, str) and q.strip() for q in search.PRESETS.values())


def test_slug_is_filesystem_safe():
    assert search.slug("EU VAT Invoice!") == "eu-vat-invoice"
    assert search.slug("") == "x"


def test_search_references_downloads_top_n_into_layout(tmp_path):
    calls = {}

    def fake_search(query, n):
        calls["query"] = query
        calls["n"] = n
        return [f"http://img/{i}.jpg" for i in range(n)]

    def fake_download(url, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"img")
        return True

    paths = search.search_references(
        ["eu vat invoice"], tmp_path, n=3,
        search_fn=fake_search, download_fn=fake_download,
    )

    assert calls["n"] == 3
    assert len(paths) == 3
    for p in paths:
        assert p.exists()
        assert p.parent == tmp_path / "_refs" / "eu-vat-invoice"


def test_search_references_skips_failed_downloads(tmp_path):
    def fake_search(query, n):
        return ["http://img/ok.jpg", "http://img/bad.jpg"]

    def fake_download(url, dest):
        if "bad" in url:
            return False
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"img")
        return True

    paths = search.search_references(
        ["q"], tmp_path, n=2, search_fn=fake_search, download_fn=fake_download,
    )
    assert len(paths) == 1
