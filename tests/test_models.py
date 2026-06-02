import pytest
from pydantic import ValidationError

from spend_predictor.models import (
    AccountChoice,
    CategorizedInvoice,
    ExtractedInvoice,
    InvoiceState,
    LineItem,
    VerificationResult,
)


def test_extracted_invoice_roundtrip():
    inv = ExtractedInvoice(
        vendor_name="Acme Cloud",
        line_items=[LineItem(description="cloud hosting", amount=100.0)],
        total=100.0,
    )
    assert inv.line_items[0].amount == 100.0
    assert inv.invoice_number is None


def test_account_choice_rejects_bad_level1():
    AccountChoice(account_code="6010", account_name="Cloud", level1="Direct", confidence=0.9, rationale="r")
    with pytest.raises(ValidationError):
        AccountChoice(account_code="6010", account_name="Cloud", level1="Maybe", confidence=0.9, rationale="r")


def test_categorized_invoice_has_hierarchy():
    c = CategorizedInvoice(
        account_code="6010", account_name="Cloud Hosting & Infrastructure",
        level1="Direct", level2="Technology", level3="Cloud Infrastructure",
        confidence=0.9, rationale="r",
    )
    assert (c.level1, c.level2, c.level3) == ("Direct", "Technology", "Cloud Infrastructure")


def test_invoice_state_defaults():
    s = InvoiceState()
    assert s.buyer_context == "" and s.product_context == ""
    assert s.skipped is False and s.errored is False and s.categorized is None


def test_verification_model():
    v = VerificationResult(arithmetic_ok=False, discrepancies=["x"], notes=None)
    assert v.discrepancies == ["x"]
