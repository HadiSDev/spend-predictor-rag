import pdfplumber
import pytest
from faker import Faker

from spend_predictor.models import ExtractedInvoice, LineItem
from spend_predictor.synthdata.render.renderer import list_templates, render_invoice_pdf
from spend_predictor.synthdata.style import build_render_spec


def _invoice() -> ExtractedInvoice:
    return ExtractedInvoice(
        vendor_name="Nimbus Cloud Services Inc.", invoice_number="INV-2026-0042",
        invoice_date="2026-05-15", currency="USD",
        line_items=[LineItem(description="Managed Kubernetes hosting", quantity=1,
                             unit_type="months", unit_price=1200.0, amount=1200.0)],
        subtotal=1200.0, tax=0.0, total=1200.0,
    )


def test_render_produces_pdf_with_key_text(tmp_path):
    out = render_invoice_pdf(_invoice(), tmp_path / "inv.pdf", buyer_name="Acme Buyer Ltd")
    assert out.exists() and out.stat().st_size > 0
    with pdfplumber.open(out) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    assert "Nimbus Cloud Services Inc." in text
    assert "INV-2026-0042" in text
    assert "1200" in text
    assert "Acme Buyer Ltd" in text


def test_classic_template_also_renders(tmp_path):
    out = render_invoice_pdf(_invoice(), tmp_path / "c.pdf", buyer_name="Acme",
                             template_name="classic")
    assert out.exists() and out.stat().st_size > 0
    with pdfplumber.open(out) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    assert "Nimbus Cloud Services Inc." in text
    assert "1200" in text


def test_list_templates_returns_sorted_names():
    templates = list_templates()
    assert isinstance(templates, list)
    assert len(templates) >= 2
    assert "modern" in templates
    assert "classic" in templates
    assert templates == sorted(templates)


def test_render_with_spec_contains_key_fields_and_extras(tmp_path):
    """Rendering WITH a RenderSpec produces PDF with vendor/invoice/total/buyer AND extras."""
    Faker.seed(99)
    fake = Faker()
    fake.seed_instance(99)

    templates = list_templates()
    spec = build_render_spec(
        fake,
        vendor_name="Nimbus Cloud Services Inc.",
        buyer_name="Acme Buyer Ltd",
        invoice_date="2026-05-15",
        vat_regime="EU",
        available_templates=templates,
    )
    # Override to a known template so we can predict behavior
    spec.template_name = "modern"
    # Ensure some optional fields are populated for testing
    spec.po_number = spec.po_number or "PO-TEST-001"
    spec.payment_terms = spec.payment_terms or "Net 30"

    out = render_invoice_pdf(
        _invoice(), tmp_path / "spec_inv.pdf",
        buyer_name="Acme Buyer Ltd",
        render_spec=spec,
    )
    assert out.exists() and out.stat().st_size > 0

    with pdfplumber.open(out) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)

    # Core fields must survive
    assert "Nimbus Cloud Services Inc." in text
    assert "INV-2026-0042" in text
    assert "1200" in text
    assert "Acme Buyer Ltd" in text

    # At least one extra field must appear
    extras_found = any([
        spec.payment_terms and spec.payment_terms in text,
        spec.po_number and spec.po_number in text,
        spec.due_date and spec.due_date in text,
    ])
    assert extras_found, "No extra fields (payment_terms / po_number / due_date) found in PDF text"


def test_render_with_spec_classic_template(tmp_path):
    """RenderSpec also works with classic template."""
    Faker.seed(77)
    fake = Faker()
    fake.seed_instance(77)

    templates = list_templates()
    spec = build_render_spec(
        fake,
        vendor_name="Nimbus Cloud Services Inc.",
        buyer_name="Acme",
        invoice_date="2026-05-15",
        vat_regime="US",
        available_templates=templates,
    )
    spec.template_name = "classic"

    out = render_invoice_pdf(
        _invoice(), tmp_path / "classic_spec.pdf",
        buyer_name="Acme",
        render_spec=spec,
    )
    assert out.exists() and out.stat().st_size > 0
    with pdfplumber.open(out) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    assert "Nimbus Cloud Services Inc." in text
    assert "1200" in text


@pytest.mark.parametrize("template", list_templates())
def test_all_templates_render_key_text(tmp_path, template):
    """Every discovered template must produce a PDF containing vendor name,
    invoice number, total amount, and buyer name — guarantees any future
    drop-in template file is covered automatically."""
    Faker.seed(42)
    fake = Faker()
    fake.seed_instance(42)

    inv = ExtractedInvoice(
        vendor_name="Nimbus Cloud Services Inc.",
        invoice_number="INV-2026-0042",
        invoice_date="2026-05-15",
        currency="USD",
        line_items=[LineItem(
            description="Managed Kubernetes hosting",
            quantity=1,
            unit_type="months",
            unit_price=1200.0,
            amount=1200.0,
        )],
        subtotal=1200.0,
        tax=0.0,
        total=1200.0,
    )
    buyer = "Acme Buyer Ltd"

    spec = build_render_spec(
        fake,
        vendor_name=inv.vendor_name,
        buyer_name=buyer,
        invoice_date=inv.invoice_date,
        vat_regime="EU",
        available_templates=list_templates(),
    )
    spec.template_name = template

    out = render_invoice_pdf(inv, tmp_path / f"{template}.pdf", buyer_name=buyer, render_spec=spec)
    assert out.exists() and out.stat().st_size > 0

    with pdfplumber.open(out) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)

    assert "Nimbus Cloud Services Inc." in text, f"[{template}] vendor_name missing"
    assert "INV-2026-0042" in text, f"[{template}] invoice_number missing"
    assert "1200" in text, f"[{template}] total amount missing"
    assert "Acme Buyer Ltd" in text, f"[{template}] buyer_name missing"
