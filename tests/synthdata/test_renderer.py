import pdfplumber

from spend_predictor.models import ExtractedInvoice, LineItem
from spend_predictor.synthdata.render.renderer import render_invoice_pdf


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
