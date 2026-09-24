"""Read a fetched document and return the lines it states.

**A document we can turn into pixels is a document we can read.** A PDF with a
text layer takes the text path, because text is cheap and exact. Everything else
we can open — a photographed receipt, a screenshot, a scan sealed inside a PDF —
is rendered and shown to the model. :class:`UnsupportedMediaError` is reserved
for what it always meant: a type we genuinely cannot open at all.

That rule replaced an earlier one which refused images outright, on the stated
grounds that reading them "needs a vision model". The deployment had been
serving a multimodal model the whole time, and half the dev org's unread
invoices were screenshots and photos that any human reads at a glance.

Two things this still deliberately does not do:

* **Guess the media type.** It comes from the ERP's own file record. Handing a
  JPEG to a PDF parser produces "Invalid PDF structure" over a document that is
  perfectly fine — our bug reported against blameless input.
* **Categorize.** Extraction produces lines; the categorizer categorizes them,
  on its own schedule, exactly as it does for every other line.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel

from web_api.connectors.base import DocumentPayload

from ..agents import make_extractor
from ..models import ExtractedInvoice, LineItem
from ..parsing import json_format_hint, parse_model
from ..pdf_loader import extract_text_from_bytes
from .images import IMAGE_MEDIA_TYPES, DocumentImage, ImageDecodeError, image_from_bytes, pdf_page_images
from .numbers import normalize_numbers

logger = logging.getLogger("ai_api.documents")

#: Media types whose text layer we try first.
_PDF_MEDIA_TYPES = {"application/pdf", "application/x-pdf"}

#: Charges printed *outside* the line table are still spend, and both paths say
#: so in the same words. €15,90 of freight on an Aquatuning invoice existed only
#: in the totals block: it was dropped on the floor — money no report could see
#: — and it was simultaneously why the extraction could not reconcile, because
#: no set of line items can sum to a total that includes a charge none of them
#: state.
#:
#: Shared by the text and vision prompts deliberately. Two copies would drift,
#: and the symptom would be scanned invoices losing freight that text ones keep,
#: with nothing in the product saying why.
#:
#: A **discount** is excluded in the same breath, because the rule invites the
#: mistake: it reduces spend rather than being spend, and a negative line would
#: flow into every report as a category with negative spend.
TOTALS_BLOCK_CHARGES = (
    "A charge printed in or beside the totals block — shipping, freight, "
    "postage, packing, handling, a payment or card fee, a surcharge — is a line "
    "item like any other, even though it sits outside the line table. Return it "
    "as a line, named as the document names it. Do NOT return a discount, a "
    "rebate or a promotion as a line, and do not return the totals themselves "
    "(subtotal, VAT, total) as lines: those have fields of their own."
)


class UnsupportedMediaError(Exception):
    """The document is fine; we have no extractor that can read this type."""


class EmptyDocumentError(Exception):
    """The document opened, but carries nothing to extract from.

    Now a genuinely empty document — a zero-page PDF — rather than a scan. A PDF
    with no text layer *has* something to extract from: its pages, as pictures.
    """


@dataclass(frozen=True)
class DocumentContent:
    """What one document gave us: text, or pictures, never both.

    A union rather than a bag of optional fields, because the two paths cost
    very different amounts and a document that produced both would leave the
    choice to whoever read the struct next.
    """

    text: str | None = None
    images: tuple[DocumentImage, ...] = ()


class ExtractedLines(BaseModel):
    """What one document said, reduced to what an invoice line needs."""

    lines: list[LineItem]
    #: The document's own stated currency, when it named one. Never used to
    #: overwrite the ledger's — the ERP posted that — only to report on.
    currency: str | None = None
    #: The supplier's invoice number as printed. Stored beside the as-posted
    #: one rather than over it: the ERP's is frequently a fallback identifier
    #: (Billy's is the bill id when the customer left the field blank), and this
    #: is the number a human reconciles against.
    invoice_number: str | None = None
    #: What the document says about its **own** arithmetic — the totals block,
    #: which was read past and discarded until now. That omission is why the
    #: only figure available to reconcile against belonged to a different
    #: system: the rule asked whether *the document's lines* added up to *the
    #: ERP's total*, two sources and two VAT conventions in one comparison.
    #:
    #: `None` means the document stated none, which is not the same as a stated
    #: zero and must never be folded into one — a document nobody could read
    #: would then look like one that balances.
    total: float | None = None
    tax: float | None = None
    subtotal: float | None = None


def _media_type(payload: DocumentPayload) -> str:
    return (payload.media_type or "").split(";")[0].strip().lower()


def document_text(payload: DocumentPayload) -> str:
    """The document's text layer.

    Still the text path's own entry point, and still strict: it answers "what
    does this document say in text", and a scan says nothing in text. Callers
    wanting the fallback to pixels use :func:`document_content`.
    """
    media_type = _media_type(payload)
    if media_type not in _PDF_MEDIA_TYPES:
        raise UnsupportedMediaError(
            f"{payload.filename}: no extractor for media type {media_type or 'unknown'!r}"
        )
    text = extract_text_from_bytes(payload.content)
    if not text.strip():
        raise EmptyDocumentError(
            f"{payload.filename}: the PDF has no extractable text layer "
            "(a scan or photo needs a vision model)"
        )
    # Danish invoices write 1919.20 as `1 919,20`. Printed beside a quantity
    # column that reads as quantity 1 and amount 919,20 — which is exactly what a
    # real Elgiganten order confirmation produced, and reconciliation then
    # rejected the whole extraction. Removing the ambiguity beats instructing the
    # model not to fall for it.
    return normalize_numbers(text)


def document_content(payload: DocumentPayload) -> DocumentContent:
    """Whatever this document can give a model, by the cheapest route available."""
    media_type = _media_type(payload)

    if media_type in _PDF_MEDIA_TYPES:
        text = extract_text_from_bytes(payload.content)
        if text.strip():
            return DocumentContent(text=normalize_numbers(text))
        # No text layer: the page *is* the document. Render it rather than
        # refusing a scan any human reads at a glance.
        pages = pdf_page_images(payload.content)
        if not pages:
            raise EmptyDocumentError(
                f"{payload.filename}: the PDF has no text layer and no pages to render"
            )
        logger.info("%s: no text layer, reading %d page(s) as images",
                    payload.filename, len(pages))
        return DocumentContent(images=tuple(pages))

    if media_type in IMAGE_MEDIA_TYPES:
        try:
            image = image_from_bytes(payload.content)
        except ImageDecodeError as exc:
            # Name the document, not the decoder: the customer can act on
            # "we could not open your file", not on a Pillow traceback.
            raise UnsupportedMediaError(
                f"{payload.filename}: declared {media_type} but the image "
                f"could not be opened ({exc})"
            ) from exc
        return DocumentContent(images=(image,))

    raise UnsupportedMediaError(
        f"{payload.filename}: no extractor for media type {media_type or 'unknown'!r}"
    )


def extract_lines(payload: DocumentPayload, *, kickoff=None, look=None) -> ExtractedLines:
    """Extract the document's invoice lines, by whichever route it supports.

    ``kickoff`` and ``look`` are the two seams the tests stub — the text
    extractor and the vision one. Both return an
    :class:`~ai_api.models.ExtractedInvoice`, so everything downstream of here
    is identical and nothing can tell how the document was read.

    The default text extractor is the same agent the PDF flow uses, prompting
    for JSON and parsing the reply rather than constraining generation: guided
    decoding on the local vLLM deployment times out under concurrency.
    """
    content = document_content(payload)

    if content.text is not None:
        run = kickoff or _kickoff_extractor
        extracted = run(
            "Extract the structured invoice data from the following invoice text. "
            "Leave any missing field null.\n\n"
            # In the prompt this function builds rather than in the agent's
            # backstory, so a test exercising the `kickoff` seam can see it. An
            # instruction only the agent carries is one no test can reach, and
            # an unreachable prompt input is one that quietly stops being sent.
            + TOTALS_BLOCK_CHARGES
            + "\n\n" + content.text
        )
    else:
        from .vision import look_at

        see = look or look_at
        extracted = see(
            "Extract the structured invoice data from the invoice shown in the "
            "following image(s). Leave any missing field null.",
            list(content.images),
        )

    return ExtractedLines(
        lines=list(extracted.line_items),
        currency=extracted.currency,
        # Blank is not a number. An empty string would read as "the document
        # states its number is ''" rather than "it states none".
        invoice_number=(extracted.invoice_number or "").strip() or None,
        # Carried through unchanged from whichever path read them. The text path
        # gets floats from a model reading text this module already normalized;
        # the vision path gets them through `parse_amount`, which is where a
        # printed figure becomes a number in this codebase. Neither is
        # re-interpreted here.
        total=extracted.total,
        tax=extracted.tax,
        subtotal=extracted.subtotal,
    )


def _kickoff_extractor(prompt: str) -> ExtractedInvoice:
    agent = make_extractor()
    result = agent.kickoff(prompt + "\n\n" + json_format_hint(ExtractedInvoice))
    return parse_model(result.raw, ExtractedInvoice)
