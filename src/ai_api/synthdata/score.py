"""Benchmark the existing pipeline against synthetic fixtures (ANLS + accuracy)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from anls import anls_score

from ..models import CategorizedInvoice, ExtractedInvoice

_STRING_FIELDS = [
    "vendor_name", "invoice_number", "currency",
    "supplier_country_code", "supplier_vat_number",
    "buyer_country_code", "buyer_vat_number", "invoice_date",
]

_NUMERIC_FIELDS = ["subtotal", "tax", "total"]


def anls_field(pred: str, gold: str) -> float:
    """ANLS similarity for one string field (0..1). Both-empty case handled by explicit guard."""
    gold = "" if gold is None else str(gold)
    pred = "" if pred is None else str(pred)
    if not gold and not pred:
        return 1.0
    return float(anls_score(prediction=pred, gold_labels=[gold], threshold=0.5))


def _num_eq(pred, gold, eps: float = 0.01) -> bool:
    """True if pred matches gold within eps (None gold treated as 0.0)."""
    gold = 0.0 if gold is None else gold
    if pred is None:
        return False
    try:
        return abs(float(pred) - float(gold)) <= eps
    except (TypeError, ValueError):
        return False


def _score_line_items(pred_lines, gold_lines) -> dict:
    """Count match + greedy best-match description ANLS + amount near-match rate."""
    n = len(gold_lines)
    count_match = len(pred_lines) == n
    if n == 0:
        return {"count_match": count_match, "desc_anls": 1.0, "amount_acc": 1.0}
    remaining = list(pred_lines)
    desc_scores: list[float] = []
    amount_hits = 0
    for g in gold_lines:
        g_desc = g.get("description") or ""
        g_amt = g.get("amount")
        if remaining:
            idx, best = max(
                enumerate(remaining),
                key=lambda kv: anls_field(getattr(kv[1], "description", "") or "", g_desc),
            )
            remaining.pop(idx)
            desc_scores.append(anls_field(getattr(best, "description", "") or "", g_desc))
            if _num_eq(getattr(best, "amount", None), g_amt):
                amount_hits += 1
        else:
            desc_scores.append(0.0)
    return {
        "count_match": count_match,
        "desc_anls": round(sum(desc_scores) / n, 4),
        "amount_acc": round(amount_hits / n, 4),
    }


def score_fixture(
    labels: dict, extracted: ExtractedInvoice | None, categorized: CategorizedInvoice | None
) -> dict:
    """Score one fixture: per-field ANLS + category exact-match booleans."""
    gold_inv = labels["invoice"]
    gold_cat = labels["category"]
    fields: dict[str, float] = {}
    for name in _STRING_FIELDS:
        gold = gold_inv.get(name) or ""
        pred = getattr(extracted, name, None) if extracted else None
        fields[name] = anls_field(pred or "", gold)

    category = {
        key: bool(categorized and getattr(categorized, key) == gold_cat[key])
        for key in ("account_code", "level1", "level2", "level3")
    }
    numeric = {
        name: _num_eq(getattr(extracted, name, None) if extracted else None, gold_inv.get(name))
        for name in _NUMERIC_FIELDS
    }
    gold_lines = gold_inv.get("line_items") or []
    pred_lines = (extracted.line_items if extracted else []) or []
    line_items = _score_line_items(pred_lines, gold_lines)
    return {"fields": fields, "numeric": numeric, "line_items": line_items, "category": category}


def _default_run_pipeline(
    pdf_path: str, buyer_context: str
) -> tuple[ExtractedInvoice | None, CategorizedInvoice | None]:  # pragma: no cover - live path
    from ..flow import InvoiceFlow
    from ..rag.indexer import build_index, load_accounts

    build_index()
    flow = InvoiceFlow()
    flow.kickoff(inputs={"pdf_path": pdf_path, "buyer_context": buyer_context,
                         "accounts": load_accounts()})
    return flow.state.extracted, flow.state.categorized


def score_fixtures(fixtures_dir: Path, *, run_pipeline=_default_run_pipeline) -> dict:
    """Run the pipeline over every fixture PDF and aggregate ANLS + accuracy."""
    fixtures_dir = Path(fixtures_dir)
    rows = []
    for fdir in sorted(p for p in fixtures_dir.iterdir() if (p / "labels.json").exists()):
        labels = json.loads((fdir / "labels.json").read_text())
        buyer = labels.get("buyer", {})
        buyer_context = f"{buyer.get('name', '')}: {buyer.get('business_description', '')}"
        try:
            extracted, categorized = run_pipeline(str(fdir / "invoice.pdf"), buyer_context)
        except Exception as exc:  # noqa: BLE001 - a pipeline failure scores as zero, not a crash
            print(f"  pipeline error on {fdir.name}: {exc}")
            extracted, categorized = None, None
        rows.append(score_fixture(labels, extracted, categorized))

    count = len(rows)
    if count == 0:
        return {
            "count": 0, "field_anls": {}, "category_accuracy": {},
            "numeric_accuracy": {}, "line_item": {},
        }

    field_anls = {
        name: round(sum(r["fields"][name] for r in rows) / count, 4)
        for name in _STRING_FIELDS
    }
    category_accuracy = {
        key: round(sum(1 for r in rows if r["category"][key]) / count, 4)
        for key in ("account_code", "level1", "level2", "level3")
    }
    numeric_accuracy = {
        name: round(sum(1 for r in rows if r["numeric"][name]) / count, 4)
        for name in _NUMERIC_FIELDS
    }
    line_item = {
        key: round(sum(r["line_items"][key] for r in rows) / count, 4)
        for key in ("count_match", "desc_anls", "amount_acc")
    }
    return {
        "count": count, "field_anls": field_anls, "category_accuracy": category_accuracy,
        "numeric_accuracy": numeric_accuracy, "line_item": line_item,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the pipeline against synthetic fixtures.")
    ap.add_argument("--fixtures", type=Path, default=Path("data/synthetic"))
    args = ap.parse_args()
    report = score_fixtures(args.fixtures)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
