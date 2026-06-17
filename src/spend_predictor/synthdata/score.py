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


def anls_field(pred: str, gold: str) -> float:
    """ANLS similarity for one string field (0..1). Empty gold or pred -> handled by anls."""
    gold = "" if gold is None else str(gold)
    pred = "" if pred is None else str(pred)
    if not gold and not pred:
        return 1.0
    return float(anls_score(prediction=pred, gold_labels=[gold], threshold=0.5))


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
    return {"fields": fields, "category": category}


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
        return {"count": 0, "field_anls": {}, "category_accuracy": {}}

    field_anls = {
        name: round(sum(r["fields"][name] for r in rows) / count, 4)
        for name in _STRING_FIELDS
    }
    category_accuracy = {
        key: round(sum(1 for r in rows if r["category"][key]) / count, 4)
        for key in ("account_code", "level1", "level2", "level3")
    }
    return {"count": count, "field_anls": field_anls, "category_accuracy": category_accuracy}


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the pipeline against synthetic fixtures.")
    ap.add_argument("--fixtures", type=Path, default=Path("data/synthetic"))
    args = ap.parse_args()
    report = score_fixtures(args.fixtures)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
