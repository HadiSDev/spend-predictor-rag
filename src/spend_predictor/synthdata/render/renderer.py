"""Render an ExtractedInvoice to a text-layer PDF via Jinja2 + WeasyPrint."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ...models import ExtractedInvoice

if TYPE_CHECKING:
    from ..style import RenderSpec

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def list_templates() -> list[str]:
    """Return sorted list of available template base-names (without .html suffix)."""
    return sorted(p.stem for p in _TEMPLATES_DIR.glob("*.html"))


def render_invoice_pdf(
    invoice: ExtractedInvoice, out_path: Path, *,
    buyer_name: str,
    render_spec: "RenderSpec | None" = None,
    template_name: str = "modern",
) -> Path:
    """Render `invoice` to a PDF at `out_path` and return the path.

    When ``render_spec`` is provided its ``template_name``, ``style``, and
    extra fields are passed into the template context.  Falls back to
    ``template_name`` (default ``"modern"``) with no style for backward
    compatibility.
    """
    from weasyprint import HTML  # local import keeps module import light

    if render_spec is not None:
        tpl = render_spec.template_name
        ctx = dict(inv=invoice, buyer_name=buyer_name,
                   style=render_spec.style, extras=render_spec)
    else:
        tpl = template_name
        ctx = dict(inv=invoice, buyer_name=buyer_name)

    html = _env.get_template(f"{tpl}.html").render(**ctx)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(str(out_path))
    return out_path
