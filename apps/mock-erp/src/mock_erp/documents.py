"""Render a generated purchase invoice to PDF bytes."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_invoice_pdf(invoice: dict) -> bytes:
    """Render one invoice dict to PDF bytes."""
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


_MEMO: dict[str, bytes] = {}


def render_for_voucher(invoice: dict) -> bytes:
    """Render an invoice PDF, memoized per voucher."""
    key = str(invoice["voucherId"])
    if key not in _MEMO:
        _MEMO[key] = render_invoice_pdf(invoice)
    return _MEMO[key]


def clear_cache() -> None:
    """Drop memoized documents."""
    _MEMO.clear()
