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
    # new fields default to None / unset
    assert inv.supplier_country_code is None and inv.buyer_vat_number is None
    assert inv.line_items[0].unit_type is None and inv.line_items[0].vat_rate is None


def test_extracted_invoice_captures_tax_and_unit_fields():
    inv = ExtractedInvoice(
        vendor_name="ACME GmbH",
        supplier_country_code="DE",
        supplier_vat_number="DE123456789",
        buyer_country_code="DK",
        buyer_vat_number="DK99887766",
        currency="EUR",
        line_items=[
            LineItem(
                description="Consulting", quantity=10, unit_type="hours",
                unit_price=120.0, amount=1200.0, vat_code="S", vat_rate=25.0,
            )
        ],
        subtotal=1200.0, tax=300.0, total=1500.0,
    )
    assert inv.supplier_country_code == "DE"
    assert inv.buyer_vat_number == "DK99887766"
    li = inv.line_items[0]
    assert (li.unit_type, li.vat_code, li.vat_rate) == ("hours", "S", 25.0)


@pytest.mark.parametrize(
    "model",
    [LineItem, ExtractedInvoice, VerificationResult, AccountChoice, CategorizedInvoice, InvoiceState],
)
def test_every_field_has_a_description(model):
    missing = [
        name for name, field in model.model_fields.items()
        if not (field.description and field.description.strip())
    ]
    assert missing == [], f"{model.__name__} fields missing Field(description=...): {missing}"


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
