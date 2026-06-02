import csv

from spend_predictor.ledger import LEDGER_COLUMNS, append_row, build_ledger_row
from spend_predictor.models import (
    CategorizedInvoice,
    ExtractedInvoice,
    LineItem,
    VerificationResult,
)


def _read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_append_writes_header_once_then_rows(tmp_path):
    ledger = tmp_path / "ledger.csv"
    append_row({"source_file": "a.pdf", "status": "processed"}, ledger)
    append_row({"source_file": "b.pdf", "status": "skipped"}, ledger)
    rows = _read(ledger)
    assert [r["source_file"] for r in rows] == ["a.pdf", "b.pdf"]
    # header written exactly once
    assert ledger.read_text().count(",".join(LEDGER_COLUMNS)) == 1


def test_build_ledger_row_processed():
    extracted = ExtractedInvoice(
        vendor_name="Acme Cloud", invoice_number="INV-1", invoice_date="2026-05-01",
        currency="USD", line_items=[LineItem(description="cloud hosting", amount=100.0)],
        subtotal=100.0, tax=0.0, total=100.0,
    )
    verification = VerificationResult(arithmetic_ok=True, discrepancies=[], notes=None)
    categorized = CategorizedInvoice(
        account_code="6010", account_name="Cloud Hosting & Infrastructure",
        level1="Direct", level2="Technology", level3="Cloud Infrastructure",
        confidence=0.9, rationale="ok",
    )
    row = build_ledger_row(
        source_file="inv.pdf", skipped=False, skip_reason="",
        extracted=extracted, verification=verification, categorized=categorized,
        buyer_name="Acme Analytics",
    )
    assert row["status"] == "processed"
    assert row["buyer_name"] == "Acme Analytics"
    assert row["level1"] == "Direct"
    assert row["level2"] == "Technology"
    assert row["account_code"] == "6010"
    assert row["arithmetic_ok"] is True


def test_build_ledger_row_errored_has_reason_and_blanks():
    row = build_ledger_row(
        source_file="boom.pdf",
        skipped=False,
        skip_reason="",
        extracted=None,
        verification=None,
        categorized=None,
        errored=True,
        error_reason="verify failed: timeout",
        buyer_name="Acme Analytics",
    )
    assert row["status"] == "error"
    assert row["notes"] == "verify failed: timeout"
    assert row["account_code"] == ""
    assert row["vendor_name"] == ""
    assert row["buyer_name"] == "Acme Analytics"


def test_build_ledger_row_skipped_has_reason_and_blanks():
    row = build_ledger_row(
        source_file="bad.pdf",
        skipped=True,
        skip_reason="empty PDF text",
        extracted=None,
        verification=None,
        categorized=None,
        buyer_name="Acme Analytics",
    )
    assert row["status"] == "skipped"
    assert row["notes"] == "empty PDF text"
    assert row["account_code"] == ""
    assert row["vendor_name"] == ""
    assert row["buyer_name"] == "Acme Analytics"
