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
    # falls back to catalog descriptions from the plan, never crashes
    assert len(inv.line_items) == len(plan.lines)
    assert all(li.description for li in inv.line_items)
    # fallback uses catalog descriptions (from plan.lines[i].description)
    expected = [l.description for l in plan.lines]
    assert [li.description for li in inv.line_items] == expected


def test_enrich_falls_back_on_unparseable_output():
    plan = sample_plans(1, seed=9, accounts=_ACCOUNTS)[0]

    def junk_generate(prompt: str) -> str:
        return "this is not json at all"

    inv = enrich_descriptions(plan, generate_fn=junk_generate)
    assert len(inv.line_items) == len(plan.lines)
    assert all(li.description for li in inv.line_items)
    # fallback uses the catalog descriptions, not "account_name item N"
    expected = [l.description for l in plan.lines]
    assert [li.description for li in inv.line_items] == expected


def test_enrich_default_no_llm_uses_catalog_descriptions():
    """With generate_fn=None (default), descriptions come from plan.lines[i].description."""
    plan = sample_plans(1, seed=42, accounts=_ACCOUNTS)[0]

    # Verify plan has catalog descriptions already populated
    assert all(l.description for l in plan.lines)

    inv = enrich_descriptions(plan)  # generate_fn defaults to None

    assert isinstance(inv, ExtractedInvoice)
    assert len(inv.line_items) == len(plan.lines)
    # All descriptions must match the plan's catalog descriptions exactly
    for i, (li, line) in enumerate(zip(inv.line_items, plan.lines)):
        assert li.description == line.description, (
            f"Line {i}: expected '{line.description}', got '{li.description}'"
        )
    # Numeric fields preserved
    assert inv.total == plan.total
    assert inv.vendor_name == plan.vendor_name


def test_enrich_default_descriptions_are_not_bare_placeholder():
    """Default path must not produce 'account_name item N' strings."""
    plan = sample_plans(1, seed=7, accounts=_ACCOUNTS)[0]
    inv = enrich_descriptions(plan)
    for li in inv.line_items:
        assert "item 1" not in li.description.lower()
        assert "item 2" not in li.description.lower()
