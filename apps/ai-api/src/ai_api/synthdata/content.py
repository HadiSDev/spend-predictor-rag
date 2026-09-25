"""Fill realistic line-item descriptions via the local model (free-text JSON)."""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from .. import config
from ..models import ExtractedInvoice, LineItem
from ..parsing import parse_model
from .sampler import InvoicePlan

try:
    from bespokelabs import curator
except ImportError:
    curator = None


class _Descriptions(BaseModel):
    descriptions: list[str] = Field(description="One short line-item description per line.")


def _build_prompt(plan: InvoicePlan, cryptic: bool) -> str:
    acct = plan.account
    style = (
        "Make each description realistic but TERSE and slightly cryptic, like a real "
        "vendor's billing label (abbreviations, SKUs)."
        if cryptic else
        "Make each description a clear, realistic product/service name."
    )
    lines = "\n".join(
        f"- line {i + 1}: quantity {l.quantity} {l.unit_type}, amount {l.amount}"
        for i, l in enumerate(plan.lines)
    )
    return (
        f"You are writing line items for an invoice from vendor '{plan.vendor_name}'.\n"
        f"All lines belong to this expense account: {acct['account_name']} "
        f"({acct['level_2']} > {acct['level_3']}) — {acct['description']}.\n"
        f"{style}\n"
        f"Write EXACTLY {len(plan.lines)} descriptions, one per line below:\n{lines}\n\n"
        'Return ONLY JSON: {"descriptions": ["...", "..."]}'
    )


def _default_generate(prompt: str) -> str:  # pragma: no cover
    """Generate free text via Bespoke Curator over the local vLLM."""
    if curator is None:
        raise ImportError(
            "Live generation needs the 'live' dependency group: run `uv sync --group live`."
        )

    llm = curator.LLM(
        model_name=config.VLLM_MODEL.replace("hosted_vllm/", ""),
        backend="vllm",
        backend_params={"base_url": config.VLLM_BASE_URL, "api_key": config.VLLM_API_KEY},
    )
    return str(llm(prompt).dataset[0]["response"])


def _generated_descriptions(
    plan: InvoicePlan, generate_fn: Callable[[str], str], cryptic: bool
) -> list[str] | None:
    """One model-written description per planned line, or ``None`` if the reply is unusable."""
    try:
        parsed = parse_model(generate_fn(_build_prompt(plan, cryptic)), _Descriptions)
    except Exception:  # noqa: BLE001
        return None
    if len(parsed.descriptions) != len(plan.lines):
        return None
    return parsed.descriptions


def enrich_descriptions(
    plan: InvoicePlan, *,
    generate_fn: Callable[[str], str] | None = None,
    cryptic: bool = False,
) -> ExtractedInvoice:
    """Return an ExtractedInvoice from the plan."""
    descriptions = [l.description for l in plan.lines]
    if generate_fn is not None:
        descriptions = _generated_descriptions(plan, generate_fn, cryptic) or descriptions

    line_items = [
        LineItem(
            description=desc, quantity=l.quantity, unit_type=l.unit_type,
            unit_price=l.unit_price, amount=l.amount, vat_code=l.vat_code, vat_rate=l.vat_rate,
        )
        for desc, l in zip(descriptions, plan.lines)
    ]
    return ExtractedInvoice(
        vendor_name=plan.vendor_name,
        supplier_country_code=plan.supplier_country_code,
        supplier_vat_number=plan.supplier_vat_number,
        buyer_country_code=plan.buyer_country_code,
        buyer_vat_number=plan.buyer_vat_number,
        invoice_number=plan.invoice_number,
        invoice_date=plan.invoice_date,
        currency=plan.currency,
        line_items=line_items,
        subtotal=plan.subtotal, tax=plan.tax, total=plan.total,
    )
