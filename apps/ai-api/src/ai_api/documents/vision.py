"""Ask the model to read an invoice it can only see — one page at a time."""
from __future__ import annotations

import base64
import logging
import re

from pydantic import BaseModel, Field

from ..config import get_llm
from ..models import ExtractedInvoice, LineItem
from ..parsing import json_format_hint, parse_model
from .errors import VisionUnreadableError
from .images import DocumentImage
from .numbers import parse_amount
from .prompts import TOTALS_BLOCK_CHARGES

logger = logging.getLogger("ai_api.documents")


_NOT_STATED = {"", "null", "none", "n/a", "na", "nil", "-", "—", "–", "unknown"}

_SUMMARY_LABELS = {
    "samlet pris", "pris i alt", "i alt", "at betale", "total dkk", "subtotal",
    "moms", "beløb", "beløb i alt", "total i alt", "sum i alt",
    "total", "sub total", "sub-total", "grand total", "sum", "amount due",
    "balance due", "order total", "total amount", "net total", "total due",
    "vat", "tax", "total excl. vat", "total incl. vat", "items subtotal",
    "item(s) subtotal",
    "gesamt", "gesamtbetrag", "zwischensumme", "summe", "mwst", "nettobetrag",
    "rechnungsbetrag",
}


def _is_summary_row(description: str | None) -> bool:
    """Is this row a total rather than a thing bought?"""
    text = (description or "").strip().lower()
    if not text:
        return False
    text = re.sub(r"[\s:.\-–—]+$", "", text)
    text = re.sub(r"\s*\(?\d+([.,]\d+)?\s*%\)?$", "", text).strip()
    text = re.sub(r"\s+(dkk|eur|usd|gbp|sek|nok)$", "", text).strip()
    return text in _SUMMARY_LABELS


def _clean(value: str | None) -> str | None:
    """A stated string, or ``None`` when the model wrote a word meaning nothing."""
    text = (value or "").strip()
    return None if text.lower() in _NOT_STATED else text


class VisionLine(BaseModel):
    """One line as the model read it off the page."""

    item_name: str | None = Field(
        default=None,
        description="The name of what was bought, as printed — the thing itself, "
        "without quantity, price or terms.",
    )
    description: str | None = Field(
        default=None,
        description="Any further prose printed on the line beyond its name. Null "
        "when the line prints only one text.",
    )
    quantity: str | float | None = Field(default=None, description="Quantity, exactly as printed.")
    unit_type: str | None = Field(default=None, description="Unit of measure, e.g. 'pcs', 'hours'.")
    unit_price: str | float | None = Field(default=None, description="Price per unit, exactly as printed.")
    amount: str | float | None = Field(
        default=None,
        description="Line total in money, exactly as printed, e.g. '1 919,20' or "
        "'kr. 58,00' — VAT-inclusive or not, whichever this line's amount column "
        "shows. Never an article number, barcode or product code.",
    )
    subtotal: str | float | None = Field(
        default=None,
        description="This line's amount NET of VAT, exactly as printed, when the "
        "line shows a net figure separately from a gross one.",
    )
    tax_amount: str | float | None = Field(
        default=None,
        description="The VAT charged on this line in money, exactly as printed.",
    )
    discount: str | float | None = Field(
        default=None,
        description="A discount printed on this line, as money, exactly as printed. "
        "Do not subtract it from the line's amount.",
    )
    vat_code: str | None = Field(default=None, description="VAT category code, if printed.")
    vat_rate: str | float | None = Field(default=None, description="VAT percentage, exactly as printed.")

    def to_line_item(self) -> LineItem:
        """Convert to the domain ``LineItem``."""
        return LineItem(
            item_name=_clean(self.item_name),
            description=_clean(self.description),
            quantity=parse_amount(self.quantity),
            unit_type=_clean(self.unit_type),
            unit_price=parse_amount(self.unit_price),
            amount=parse_amount(self.amount),
            subtotal=parse_amount(self.subtotal),
            tax_amount=parse_amount(self.tax_amount),
            discount=parse_amount(self.discount),
            vat_code=_clean(self.vat_code),
            vat_rate=parse_amount(self.vat_rate),
        )


class VisionPage(BaseModel):
    """What one page of a document states."""

    vendor_name: str | None = Field(default=None, description="Supplier (seller) company name.")
    supplier_country_code: str | None = Field(default=None, description="Supplier country, ISO 3166-1 alpha-2.")
    supplier_vat_number: str | None = Field(default=None, description="Supplier VAT registration number.")
    buyer_country_code: str | None = Field(default=None, description="Buyer country, ISO 3166-1 alpha-2.")
    buyer_vat_number: str | None = Field(default=None, description="Buyer VAT registration number.")
    invoice_number: str | None = Field(default=None, description="Invoice number as printed.")
    invoice_date: str | None = Field(default=None, description="Invoice date; ISO 8601 if parseable, else as printed.")
    currency: str | None = Field(default=None, description="ISO 4217 currency code, e.g. 'DKK', 'EUR', 'USD'.")
    line_items: list[VisionLine] = Field(
        default_factory=list,
        description="The line items printed on this page, each amount as printed.",
    )
    subtotal: str | float | None = Field(default=None, description="Net total excluding VAT as printed, if shown here.")
    tax: str | float | None = Field(default=None, description="VAT amount as printed, if shown here.")
    total: str | float | None = Field(default=None, description="Gross total as printed, if shown here.")


_INSTRUCTIONS = (
    "You are reading a supplier invoice or receipt. It is shown to you as an "
    "image. Transcribe what the document states — do not infer, compute or "
    "invent anything it does not show.\n"
    "\n"
    "Return every line item visible here, with its name and its amount. "
    "Leave any field this page does not state as null.\n"
    "\n"
    "A line's name is the product or service itself — 'Figma Organization seat', "
    "'Consulting', 'DJI Osmo Nano 128GB' — with no quantity, price, date or "
    "contract term in it. If the line prints further prose beyond that name, put "
    "it in the description. If the line prints only one text, put it in the name "
    "and leave the description null. Never invent a description.\n"
    "\n"
    "Take the line items from the table that carries prices — the one with a "
    "quantity, unit price or amount column. Rows without any money value, such "
    "as a travel itinerary, a delivery schedule or an address block, are not "
    "line items.\n"
    "\n"
    "Copy every number EXACTLY as printed, as a string, including its separators "
    "and any currency symbol: write \"1 919,20\", \"5.780,00\" or \"kr. 58,00\" "
    "verbatim. Do not convert, reformat, round or compute anything — the "
    "separators are read afterwards, and rewriting them destroys the evidence.\n"
    "\n"
    "A line's amount is the money charged for that line. Its column is the one "
    "carrying money — headed 'Amount', 'Subtotal', 'Total', 'Price', 'Line "
    "total', 'Beløb', 'Pris', 'Sum' or similar — and its values usually carry a "
    "currency symbol or decimals. An article number, product code, barcode, EAN "
    "or SKU is never an amount, however close its column sits to the price: if a "
    "line shows no money value, leave its amount null.\n"
    "\n"
    "Report the currency the document itself prints as an ISO 4217 code — 'kr' "
    "on a Danish document is 'DKK' — since that may differ from the currency it "
    "was booked in.\n"
    "\n"
    + TOTALS_BLOCK_CHARGES
)

_PAGE_NOTE = (
    "This is page {page} of {total} of one invoice. Report only what this page "
    "shows. Do not carry over or guess at lines printed on the other pages, and "
    "leave totals null unless they are printed here."
)


def _data_url(image: DocumentImage) -> str:
    encoded = base64.b64encode(image.content).decode("ascii")
    return f"data:{image.media_type};base64,{encoded}"


def build_messages(image: DocumentImage, *, page: int = 1, total: int = 1) -> list[dict]:
    """The chat messages for one page."""
    text = _INSTRUCTIONS
    if total > 1:
        text += "\n\n" + _PAGE_NOTE.format(page=page, total=total)
    text += "\n\n" + json_format_hint(VisionPage)
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": _data_url(image)}},
            ],
        }
    ]


def _default_complete(messages: list[dict]) -> str:
    return get_llm().call(messages)


_FIRST_WINS = (
    "vendor_name",
    "supplier_country_code",
    "supplier_vat_number",
    "buyer_country_code",
    "buyer_vat_number",
    "invoice_number",
    "invoice_date",
    "currency",
)

_LAST_WINS = ("subtotal", "tax", "total")


def _merge(pages: list[VisionPage]) -> ExtractedInvoice:
    """Fold per-page readings into the one invoice they describe."""
    merged: dict = {}
    for field in _FIRST_WINS:
        merged[field] = next(
            (value for page in pages if (value := _clean(getattr(page, field))) is not None),
            None,
        )
    for field in _LAST_WINS:
        merged[field] = next(
            (
                value
                for page in reversed(pages)
                if (value := parse_amount(getattr(page, field))) is not None
            ),
            None,
        )
    merged["vendor_name"] = merged.get("vendor_name") or ""
    stated = [item for page in pages for item in page.line_items]
    itemised = [
        item for item in stated
        if not _is_summary_row(item.item_name or item.description)
    ]
    merged["line_items"] = [item.to_line_item() for item in (itemised or stated)]
    return ExtractedInvoice(**merged)


def look_at(prompt: str, images: list[DocumentImage], *, complete=None) -> ExtractedInvoice:
    """Read the document in ``images``, one page per request, and merge."""
    ask = complete or _default_complete
    total = len(images)
    pages: list[VisionPage] = []

    for index, image in enumerate(images, start=1):
        messages = build_messages(image, page=index, total=total)
        try:
            reply = ask(messages)
            pages.append(parse_model(reply, VisionPage))
        except Exception as exc:  # noqa: BLE001
            logger.warning("vision: page %d of %d could not be read: %s", index, total, exc)

    if not pages:
        raise VisionUnreadableError(
            f"none of the {total} page(s) of this document could be read"
        )
    if len(pages) < total:
        logger.warning(
            "vision: read %d of %d page(s); the extraction is incomplete and "
            "reconciliation will judge it",
            len(pages), total,
        )
    return _merge(pages)
