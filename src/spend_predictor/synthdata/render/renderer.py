"""Render an ExtractedInvoice to a text-layer PDF via Jinja2 + WeasyPrint."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ...models import ExtractedInvoice

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_invoice_pdf(
    invoice: ExtractedInvoice, out_path: Path, *,
    buyer_name: str, template_name: str = "modern",
) -> Path:
    """Render `invoice` to a PDF at `out_path` and return the path."""
    from weasyprint import HTML  # local import keeps module import light

    html = _env.get_template(f"{template_name}.html").render(inv=invoice, buyer_name=buyer_name)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(str(out_path))
    return out_path
