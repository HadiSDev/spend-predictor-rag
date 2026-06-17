# tests/synthdata/test_generate.py
import json

from spend_predictor.synthdata.generate import generate_dataset

_ACCOUNTS = [{"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
              "level2": "Technology", "level3": "Cloud Infrastructure", "description": "cloud"}]


def test_generate_writes_bundles_and_manifest(tmp_path, monkeypatch):
    import spend_predictor.synthdata.generate as gen

    # Offline: deterministic chart, stub enrichment, fake renderer (no WeasyPrint).
    monkeypatch.setattr(gen, "load_accounts", lambda: _ACCOUNTS)

    def fake_enrich(plan, cryptic=False):
        from spend_predictor.synthdata.content import enrich_descriptions
        return enrich_descriptions(plan, generate_fn=lambda p: '{"descriptions": ' +
                                   json.dumps([f"item {i}" for i in range(len(plan.lines))]) + '}')

    def fake_render(invoice, out_path, *, buyer_name, render_spec=None, template_name="modern"):
        from pathlib import Path
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)

    n = generate_dataset(3, seed=7, out_dir=tmp_path, enrich_fn=fake_enrich, render_fn=fake_render)

    assert n == 3
    manifest = (tmp_path / "manifest.jsonl").read_text().splitlines()
    assert len(manifest) == 3
    for entry in (json.loads(line) for line in manifest):
        fdir = tmp_path / entry["id"]
        assert (fdir / "invoice.pdf").exists()
        labels = json.loads((fdir / "labels.json").read_text())
        assert labels["category"]["account_code"] == "6010"
        assert labels["invoice"]["line_items"]


def test_generate_skips_failed_items_without_aborting(tmp_path, monkeypatch):
    import spend_predictor.synthdata.generate as gen
    monkeypatch.setattr(gen, "load_accounts", lambda: _ACCOUNTS)

    calls = {"n": 0}

    def flaky_render(invoice, out_path, *, buyer_name, render_spec=None, template_name="modern"):
        from pathlib import Path
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("render boom")
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)

    def fake_enrich(plan, cryptic=False):
        from spend_predictor.synthdata.content import enrich_descriptions
        return enrich_descriptions(plan, generate_fn=lambda p: '{"descriptions": ' +
                                   json.dumps(["x" for _ in plan.lines]) + '}')

    n = generate_dataset(3, seed=1, out_dir=tmp_path, enrich_fn=fake_enrich, render_fn=flaky_render)
    assert n == 2  # one item failed and was skipped, batch continued
    assert len((tmp_path / "manifest.jsonl").read_text().splitlines()) == 2
