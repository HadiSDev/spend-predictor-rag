# tests/synthdata/test_erp.py
from spend_predictor.models import ExtractedInvoice, LineItem
from spend_predictor.synthdata.erp import build_journal


def _invoice(tax: float) -> ExtractedInvoice:
    return ExtractedInvoice(
        vendor_name="ACME", line_items=[LineItem(description="x", amount=100.0)],
        subtotal=100.0, tax=tax, total=round(100.0 + tax, 2),
    )


def test_journal_balances_with_vat():
    j = build_journal(_invoice(25.0), "6010", "Cloud Hosting & Infrastructure")
    assert round(sum(e.debit for e in j), 2) == round(sum(e.credit for e in j), 2) == 125.0
    expense = next(e for e in j if e.account_code == "6010")
    assert expense.debit == 100.0
    assert any(e.account_code == "1300" and e.debit == 25.0 for e in j)   # VAT input
    assert any(e.account_code == "2000" and e.credit == 125.0 for e in j)  # AP


def test_journal_balances_without_vat():
    j = build_journal(_invoice(0.0), "6800", "Travel - Airfare")
    assert round(sum(e.debit for e in j), 2) == round(sum(e.credit for e in j), 2) == 100.0
    assert not any(e.account_code == "1300" for e in j)  # no VAT line when tax is 0
