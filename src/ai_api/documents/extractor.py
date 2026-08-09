"""Read a fetched document and return the lines it states.

Two things this deliberately does not do:

* **Guess the media type.** It comes from the ERP's own file record, and the
  dispatch is on that. A good share of real Billy attachments are phone photos
  of a receipt, and handing a JPEG to a PDF parser produces "Invalid PDF
  structure" over a document that is perfectly fine — a confusing failure
  against blameless input.
* **Categorize.** Extraction produces lines; the categorizer categorizes them,
  on its own schedule, exactly as it does for every other line.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

from web_api.connectors.base import DocumentPayload

from ..agents import make_extractor
from ..models import ExtractedInvoice, LineItem
from ..parsing import json_format_hint, parse_model
from ..pdf_loader import extract_text_from_bytes

logger = logging.getLogger("ai_api.documents")

#: Media types we can turn into text today. An image needs a vision model; until
#: one is deployed, an image records a clean unsupported-media failure rather
#: than a misleading parse error, and keeps its stand-in lines.
_PDF_MEDIA_TYPES = {"application/pdf", "application/x-pdf"}


class UnsupportedMediaError(Exception):
    """The document is fine; we have no extractor that can read this type."""


class EmptyDocumentError(Exception):
    """The document parsed, but carries no text to extract from."""


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


def document_text(payload: DocumentPayload) -> str:
    """The document's text, dispatched on the media type the ERP declared."""
    media_type = (payload.media_type or "").split(";")[0].strip().lower()
    if media_type in _PDF_MEDIA_TYPES:
        text = extract_text_from_bytes(payload.content)
        if not text.strip():
            # A scanned-image PDF: valid, parseable, and carrying no text layer.
            # Same answer as an image — we cannot read it without a vision model.
            raise EmptyDocumentError(
                f"{payload.filename}: the PDF has no extractable text layer "
                "(a scan or photo needs a vision model)"
            )
        return text
    raise UnsupportedMediaError(
        f"{payload.filename}: no extractor for media type {media_type or 'unknown'!r}"
    )


def extract_lines(payload: DocumentPayload, *, kickoff=None) -> ExtractedLines:
    """Extract the document's invoice lines.

    ``kickoff`` is the seam the tests stub: it takes the prompt text and returns
    an :class:`~ai_api.models.ExtractedInvoice`. The default runs the same
    extraction agent the PDF flow uses, prompting for JSON and parsing the reply
    rather than constraining generation — guided decoding on the local vLLM
    deployment times out under concurrency.
    """
    text = document_text(payload)
    run = kickoff or _kickoff_extractor
    extracted = run(
        "Extract the structured invoice data from the following invoice text. "
        "Leave any missing field null.\n\n" + text
    )
    return ExtractedLines(
        lines=list(extracted.line_items),
        currency=extracted.currency,
        # Blank is not a number. An empty string would read as "the document
        # states its number is ''" rather than "it states none".
        invoice_number=(extracted.invoice_number or "").strip() or None,
    )


def _kickoff_extractor(prompt: str) -> ExtractedInvoice:
    agent = make_extractor()
    result = agent.kickoff(prompt + "\n\n" + json_format_hint(ExtractedInvoice))
    return parse_model(result.raw, ExtractedInvoice)
