"""Validate a drafted template: renders cleanly + has the contract placeholders
+ contains no real data. Used to gate drafts before a human reviews them."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, select_autoescape

from ...models import ExtractedInvoice
from ..content import enrich_descriptions
from ..sampler import sample_plans
from ..style import RenderSpec


@dataclass
class ValidationResult:
    ok: bool
    reasons: list[str]


def sample_render_inputs() -> tuple[ExtractedInvoice, str, RenderSpec]:
    """Deterministic (invoice, buyer_name, render_spec) for rendering — no LLM."""
    plan = sample_plans(1, seed=0)[0]
    invoice = enrich_descriptions(plan)  # generate_fn=None -> catalog text, no LLM
    return invoice, plan.buyer.name, plan.render


def try_render(html: str, out_path: Path | None = None) -> str | None:
    """Render `html` with the sample inputs. Return None on success, else a reason."""
    invoice, buyer_name, render_spec = sample_render_inputs()
    env = Environment(autoescape=select_autoescape(["html"]))
    try:
        rendered = env.from_string(html).render(
            inv=invoice, buyer_name=buyer_name,
            style=render_spec.style, extras=render_spec,
        )
        from weasyprint import HTML  # local import keeps module light
        pdf = HTML(string=rendered).write_pdf()
        if out_path is not None:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(pdf)
    except Exception as exc:  # noqa: BLE001 - reason is the message
        return f"render failed: {exc}"
    return None


def contract_check(html: str) -> list[str]:
    """Reasons for any missing required placeholder."""
    reasons: list[str] = []
    if "inv.vendor_name" not in html:
        reasons.append("missing vendor placeholder {{ inv.vendor_name }}")
    if "inv.total" not in html:
        reasons.append("missing total placeholder {{ inv.total }}")
    if not re.search(r"{%\s*for\s+\w+\s+in\s+inv\.line_items", html):
        reasons.append("missing line-item loop {% for li in inv.line_items %}")
    return reasons


_EMAIL_RE = re.compile(r"[\w.+-]+@[a-zA-Z][\w-]*\.[a-zA-Z]{2,}")
_DIGITS_RE = re.compile(r"\d{4,}")
_IMG_URL_RE = re.compile(r"""(src\s*=\s*['"]?\s*https?:|url\(\s*['"]?\s*https?:|data:image)""",
                         re.IGNORECASE)
_STYLE_RE = re.compile(r"<style.*?</style>", re.DOTALL | re.IGNORECASE)
_JINJA_RE = re.compile(r"{{.*?}}|{%.*?%}", re.DOTALL)


def lint_no_real_data(html: str) -> list[str]:
    """Reasons for any sign of copied real data."""
    reasons: list[str] = []
    # Image-URL / embedded-logo check runs on the FULL html (CSS included).
    if _IMG_URL_RE.search(html):
        reasons.append("external or data: image URL (possible real logo)")
    # Email / digit checks run on visible text only: strip <style> and Jinja tags
    # so CSS pixel values and placeholder expressions don't false-positive.
    text = _JINJA_RE.sub(" ", _STYLE_RE.sub(" ", html))
    if _EMAIL_RE.search(text):
        reasons.append("email address in template text")
    if _DIGITS_RE.search(text):
        reasons.append("run of >=4 digits in template text (possible real number)")
    return reasons


def validate_template(html: str) -> ValidationResult:
    """Run render + contract + lint. ok only if all pass."""
    reasons: list[str] = []
    render_reason = try_render(html)
    if render_reason is not None:
        reasons.append(render_reason)
    reasons.extend(contract_check(html))
    reasons.extend(lint_no_real_data(html))
    return ValidationResult(ok=not reasons, reasons=reasons)
