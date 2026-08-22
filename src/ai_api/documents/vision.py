"""Ask the model to read an invoice it can only see — one page at a time.

The same deployment and the same JSON discipline as the text path — one model,
one config, one timeout — differing only in what rides in the message: pictures
instead of a text layer. CrewAI's ``LLM.call`` passes an OpenAI-style content
list straight through to the provider, so no second client is needed and no
second place can drift out of sync with :func:`ai_api.config.get_llm`.

**Each page is its own request.** A model handed eight images in one message
attends to none of them properly, and what degrades first is exactly what an
invoice is made of: an amount, in a column, in small type. Per-page costs more
requests and buys back the model's full attention on each. The pages are then
merged *here*, in code, rather than by asking the model to hold a whole document
in its head — merging is arithmetic and bookkeeping, which is not what a vision
model is for.

**A page is a fragment, so :class:`VisionPage` requires nothing.** That is not a
convenience, it is the fix for the bug that made every real screenshot fail. The
prompt tells the model to leave what a page does not state as null; page 3 of 5
names no supplier and prints no total, and the model said so, correctly, in
well-formed JSON. Validating that against :class:`~ai_api.models.ExtractedInvoice`
— whose ``vendor_name`` and ``total`` are mandatory, as they should be for a
whole invoice — threw away a perfectly good reading and reported it as a model
failure. The whole-invoice requirements apply to the merge, never to a page.

Two more rules make the merge safe:

* A **header** field (supplier, invoice number, currency) is taken from the
  first page that states it; a **total** from the last. That is where each is
  printed, and a page that omits one must not erase what another page said.
* An **unreadable page does not discard the readable ones**. A terms-and-
  conditions page returning junk must not lose a good first page. Every dropped
  page is logged — never silently skipped — and reconciliation is the backstop
  that catches an incomplete read. A document whose pages *all* fail is a
  failure, because then we have read nothing at all.

**Numbers are transcribed, not interpreted.** The text path removes European
number ambiguity *before* the model sees it (:mod:`ai_api.documents.numbers`
rewrites ``1 919,20`` to ``1919.20``, after a real Elgiganten order confirmation
was read as quantity ``1`` and amount ``919,20``). Pixels cannot be rewritten,
so this path does the same job on the way back: :class:`VisionLine` takes every
figure as a **string, exactly as printed**, and
:func:`~ai_api.documents.numbers.parse_amount` decides what it means. Asking the
model to normalize separators itself was tried first and lost — a DSB receipt
printing ``5.780,00`` came back as ``5.78``. Both paths now end at the same
tested pure function, and neither leaves the decision in a prompt.

What a prompt still cannot fix is *which column* holds the money. An EKWB credit
memo prints its amounts under a ``Subtotal`` heading beside a ``Sku`` column of
barcodes, and the model first returned the barcodes and now returns nulls.
``parse_amount`` refuses a 13-digit article number outright, so the wrong answer
became no answer — which reconciliation catches — but a small vision model
reading a wide table remains this path's real limit.
"""
from __future__ import annotations

import base64
import logging
import re

from pydantic import BaseModel, Field

from ..models import ExtractedInvoice, LineItem
from ..parsing import json_format_hint, parse_model
from .images import DocumentImage
from .numbers import parse_amount

logger = logging.getLogger("ai_api.documents")


class VisionUnreadableError(Exception):
    """Not one page of the document produced a usable answer."""


#: Words a model writes when it means "nothing here". A literal `"null"` string
#: arrived as a real reply's currency; left alone it becomes a currency code.
_NOT_STATED = {"", "null", "none", "n/a", "na", "nil", "-", "—", "–", "unknown"}

#: Labels that mark a row as a *summary of other rows* rather than a thing
#: bought. Two DSB receipts, identical in shape, settled this: one was read as a
#: single `1 Voksen` line and reconciled, the other returned `1 Voksen` **and**
#: `Samlet pris` — double the posting — and was rejected, keeping its ERP
#: stand-in. Whether a total is an item is not a judgement worth making twice.
#:
#: Danish, English and German, because that is what this ledger's suppliers
#: invoice in. Deliberately excludes shipping, postage, handling and fees: those
#: are billed money inside the total, and dropping them would fail every invoice
#: that carries any.
_SUMMARY_LABELS = {
    # Danish
    "samlet pris", "pris i alt", "i alt", "at betale", "total dkk", "subtotal",
    "moms", "beløb", "beløb i alt", "total i alt", "sum i alt",
    # English
    "total", "sub total", "sub-total", "grand total", "sum", "amount due",
    "balance due", "order total", "total amount", "net total", "total due",
    "vat", "tax", "total excl. vat", "total incl. vat", "items subtotal",
    "item(s) subtotal",
    # German
    "gesamt", "gesamtbetrag", "zwischensumme", "summe", "mwst", "nettobetrag",
    "rechnungsbetrag",
}


def _is_summary_row(description: str | None) -> bool:
    """Is this row a total rather than a thing bought?

    Matched on the **whole** label, never as a substring: "Total Station Kit" is
    a surveying instrument and "Sumatra coffee" is a coffee. Silently deleting a
    real line would be a far worse bug than the double-count this prevents, so
    the rule stays narrow and a trailing colon, percentage or currency code is
    all it will look past.
    """
    text = (description or "").strip().lower()
    if not text:
        # Blank is not a summary word. A line with no description is ordinary —
        # half of Billy's bill lines carry none.
        return False
    # Trim the decoration a total is printed with: `Total:`, `Moms 25%`,
    # `Total EUR`, `Sum (incl. VAT)`.
    text = re.sub(r"[\s:.\-–—]+$", "", text)
    text = re.sub(r"\s*\(?\d+([.,]\d+)?\s*%\)?$", "", text).strip()
    text = re.sub(r"\s+(dkk|eur|usd|gbp|sek|nok)$", "", text).strip()
    return text in _SUMMARY_LABELS


def _clean(value: str | None) -> str | None:
    """A stated string, or ``None`` when the model wrote a word meaning nothing."""
    text = (value or "").strip()
    return None if text.lower() in _NOT_STATED else text


class VisionLine(BaseModel):
    """One line as the model read it off the page.

    **Every number is a string here, deliberately.** The text path removes
    European number ambiguity before the model ever sees it; pixels cannot be
    rewritten, so this path does the same job on the way back — the model
    transcribes the figure exactly as printed and
    :func:`~ai_api.documents.numbers.parse_amount` decides what it means. That
    moves the decision out of a prompt and into a tested pure function, which is
    the only reason `5.780,00` stops coming back as `5.78`.
    """

    description: str | None = Field(default=None, description="What was bought, as printed.")
    quantity: str | float | None = Field(default=None, description="Quantity, exactly as printed.")
    unit_type: str | None = Field(default=None, description="Unit of measure, e.g. 'pcs', 'hours'.")
    unit_price: str | float | None = Field(default=None, description="Price per unit, exactly as printed.")
    amount: str | float | None = Field(
        default=None,
        description="Line total in money, exactly as printed, e.g. '1 919,20' or "
        "'kr. 58,00'. Never an article number, barcode or product code.",
    )
    vat_code: str | None = Field(default=None, description="VAT category code, if printed.")
    vat_rate: str | float | None = Field(default=None, description="VAT percentage, exactly as printed.")

    def to_line_item(self) -> LineItem:
        """The domain line. An unreadable amount becomes no amount, never a guess."""
        return LineItem(
            description=_clean(self.description) or "",
            quantity=parse_amount(self.quantity),
            unit_type=_clean(self.unit_type),
            unit_price=parse_amount(self.unit_price),
            amount=parse_amount(self.amount),
            vat_code=_clean(self.vat_code),
            vat_rate=parse_amount(self.vat_rate),
        )


class VisionPage(BaseModel):
    """What one page of a document states.

    Every field is optional, and that is the point: a page is a fragment. Page 3
    of 5 names no supplier and prints no total, and a schema that demands them
    turns the model's correct answer into a parse failure. The fields mirror
    :class:`~ai_api.models.ExtractedInvoice` so the merge is a field-for-field
    fold with nothing to translate.
    """

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
    "Return every line item visible here, with its description and its amount. "
    "Leave any field this page does not state as null.\n"
    "\n"
    # Deliberately NOT told to exclude summary rows. That instruction was tried
    # and made things worse: on a DSB receipt it pushed the model off the product
    # table ("1 Voksen 58,00") and onto the itinerary above it, returning three
    # journey legs with no amounts where it had previously returned the item and
    # its total. Dropping the total is `_is_summary_row`'s job — it is a fact in
    # tested code, and asking for it here only made the harder judgement (which
    # table holds the items) come out wrong.
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
    "was booked in."
)

#: Said only when there is more than one page. Telling a single-page document it
#: is "page 1 of 1" invites the model to hedge about content it can see in full.
_PAGE_NOTE = (
    "This is page {page} of {total} of one invoice. Report only what this page "
    "shows. Do not carry over or guess at lines printed on the other pages, and "
    "leave totals null unless they are printed here."
)


def _data_url(image: DocumentImage) -> str:
    encoded = base64.b64encode(image.content).decode("ascii")
    return f"data:{image.media_type};base64,{encoded}"


def build_messages(image: DocumentImage, *, page: int = 1, total: int = 1) -> list[dict]:
    """The chat messages for one page. Public so a prompt change reviews alone."""
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
    from ..config import get_llm

    return get_llm().call(messages)


#: Header fields printed once, at the front. First page to state one wins; a
#: later page's silence must not erase it, and a later page's restatement adds
#: nothing. `total` is deliberately absent — see `_LAST_WINS`.
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

#: Figures printed at the end. An earlier page's total is a running subtotal, so
#: the last page to state one is the document's own answer.
_LAST_WINS = ("subtotal", "tax", "total")


def _merge(pages: list[VisionPage]) -> ExtractedInvoice:
    """Fold per-page readings into the one invoice they describe.

    This is where the whole-invoice requirements finally apply: a fragment may
    omit anything, an invoice may not.
    """
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
    # `total` and `vendor_name` are mandatory on a whole invoice. No page stating
    # a total means zero, which reconciliation then rejects against the ledger —
    # the right outcome, and a visible one.
    merged["total"] = merged.get("total") or 0.0
    merged["vendor_name"] = merged.get("vendor_name") or ""
    # Never deduplicated: a supplier who billed the same item twice billed it
    # twice, and collapsing that is a correction we have no standing to make.
    # A total is not a line item: `Samlet pris` beside `1 Voksen` doubled a DSB
    # receipt against its own posting and cost us the document entirely.
    #
    # Judged across the whole document, not per page — a multi-page invoice
    # prints its items early and its total last, and a page-local rule would
    # keep the total whenever it arrived alone on the final page.
    stated = [item for page in pages for item in page.line_items]
    itemised = [item for item in stated if not _is_summary_row(item.description)]
    # …unless the totals were all we were given. The filter exists to stop
    # double-counting, and with nothing left to double-count it has no work to
    # do: a lone total can only equal the document's own total, so keeping it
    # cannot inflate anything, while dropping it throws the document away and
    # leaves the invoice on an ERP stand-in that says less.
    merged["line_items"] = [item.to_line_item() for item in (itemised or stated)]
    return ExtractedInvoice(**merged)


def look_at(prompt: str, images: list[DocumentImage], *, complete=None) -> ExtractedInvoice:
    """Read the document in ``images``, one page per request, and merge.

    ``prompt`` is accepted for symmetry with the text path's seam and is
    deliberately unused: the text path's prompt *carries the document*, and
    there is nothing here to carry. Keeping the signature identical is what lets
    :func:`ai_api.documents.extractor.extract_lines` treat the two as one shape.

    ``complete`` is the seam the tests stub: it takes chat messages and returns
    the model's text.
    """
    ask = complete or _default_complete
    total = len(images)
    pages: list[VisionPage] = []

    for index, image in enumerate(images, start=1):
        messages = build_messages(image, page=index, total=total)
        try:
            reply = ask(messages)
            pages.append(parse_model(reply, VisionPage))
        except Exception as exc:  # noqa: BLE001 - one bad page is not a bad document
            # Logged, never silent: an incomplete read that reconciles by luck
            # would otherwise look like a clean one.
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
