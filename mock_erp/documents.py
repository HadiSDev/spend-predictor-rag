"""Render a generated purchase invoice to PDF bytes.

The document is rendered from the *same* dict the invoice endpoints serve, so
the scan a reviewer reads always agrees with the rows that were synced from it.
A document that disagreed with its data would make the correction UI untestable.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_invoice_pdf(invoice: dict) -> bytes:
    """Render one invoice dict to PDF bytes."""
    # Local import: WeasyPrint pulls in heavy native deps, and importing this
    # module must stay cheap for callers that never render. Mirrors
    # ai_api/synthdata/render/renderer.py.
    from weasyprint import HTML

    html = _env.get_template("invoice.html").render(
        supplier=invoice["supplier"],
        invoice_number=invoice["purchaseInvoiceNumber"],
        voucher_id=invoice["voucherId"],
        date=invoice["date"],
        currency=invoice["currency"],
        lines=invoice.get("lines", []),
        net=invoice["netAmount"],
        vat=invoice["vatAmount"],
        gross=invoice["grossAmount"],
    )
    return HTML(string=html).write_pdf()


def render_for_voucher(invoice: dict) -> bytes:
    """Render with a per-voucher memo. Rendering costs ~100ms and the data is
    static between regenerations, so the same voucher is only ever rendered once.
    """
    key = str(invoice["voucherId"])
    if key not in _MEMO:
        _MEMO[key] = render_invoice_pdf(invoice)
    return _MEMO[key]


_MEMO: dict[str, bytes] = {}


def clear_cache() -> None:
    """Drop memoized documents. Called when the mock regenerates its data."""
    _MEMO.clear()
