from spend_predictor.models import (
    CategorizedInvoice,
    ExtractedInvoice,
    InvoiceState,
    LineItem,
    VerificationResult,
)


def test_extracted_invoice_roundtrip():
    inv = ExtractedInvoice(
        vendor_name="Acme Cloud",
        invoice_number="INV-1",
        invoice_date="2026-05-01",
        currency="USD",
        line_items=[LineItem(description="cloud hosting", quantity=1, unit_price=100.0, amount=100.0)],
        subtotal=100.0,
        tax=0.0,
        total=100.0,
    )
    assert inv.line_items[0].amount == 100.0
    assert inv.total == 100.0


def test_optional_fields_default_to_none():
    inv = ExtractedInvoice(vendor_name="X", line_items=[], total=0.0)
    assert inv.invoice_number is None
    assert inv.subtotal is None


def test_invoice_state_constructs_with_defaults():
    state = InvoiceState()
    assert state.pdf_path == ""
    assert state.skipped is False
    assert state.extracted is None


def test_verification_and_categorization_models():
    v = VerificationResult(arithmetic_ok=False, discrepancies=["total mismatch"], notes=None)
    c = CategorizedInvoice(
        account_code="6010", account_name="Cloud Hosting", category="IT", confidence=0.9, rationale="ok"
    )
    assert v.discrepancies == ["total mismatch"]
    assert c.account_code == "6010"
