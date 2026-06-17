import json

from spend_predictor.models import ExtractedInvoice
from spend_predictor.synthdata.content import enrich_descriptions
from spend_predictor.synthdata.sampler import sample_plans

_ACCOUNTS = [{"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
              "level2": "Technology", "level3": "Cloud Infrastructure", "description": "cloud servers"}]


def test_enrich_fills_descriptions_and_preserves_labels():
    plan = sample_plans(1, seed=2, accounts=_ACCOUNTS)[0]
    captured = {}

    def fake_generate(prompt: str) -> str:
        captured["prompt"] = prompt
        descs = [f"Item {i}" for i in range(len(plan.lines))]
        return json.dumps({"descriptions": descs})

    inv = enrich_descriptions(plan, generate_fn=fake_generate)

    assert isinstance(inv, ExtractedInvoice)
    assert [li.description for li in inv.line_items] == [f"Item {i}" for i in range(len(plan.lines))]
    # numeric/label fields come straight from the plan, untouched by the LLM
    assert inv.total == plan.total and inv.subtotal == plan.subtotal
    assert inv.vendor_name == plan.vendor_name
    assert len(inv.line_items) == len(plan.lines)
    assert inv.line_items[0].amount == plan.lines[0].amount
    assert "Cloud Hosting & Infrastructure" in captured["prompt"]  # account context given


def test_enrich_falls_back_when_count_mismatch():
    plan = sample_plans(1, seed=5, accounts=_ACCOUNTS)[0]

    def bad_generate(prompt: str) -> str:
        return '{"descriptions": ["only one"]}'  # wrong count

    inv = enrich_descriptions(plan, generate_fn=bad_generate)
    # falls back to a deterministic per-line placeholder, never crashes
    assert len(inv.line_items) == len(plan.lines)
    assert all(li.description for li in inv.line_items)
