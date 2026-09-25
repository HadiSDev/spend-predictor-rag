"""Flow state for processing a single invoice."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .categorization import CategorizedInvoice
from .invoice import ExtractedInvoice, VerificationResult


class InvoiceState(BaseModel):
    """Flow state for processing a single invoice."""

    pdf_path: str = Field(
        default="", description="Filesystem path to the invoice PDF being processed."
    )
    invoice_text: str = Field(
        default="", description="Raw text extracted from the PDF."
    )
    buyer_context: str = Field(
        default="",
        description="Buyer business context (scraped once per batch) used to judge "
        "Direct/Indirect.",
    )
    product_context: str = Field(
        default="", description="Per-invoice product/web context for the line items."
    )
    accounts: list[dict] = Field(
        default_factory=list,
        description="Chart-of-accounts rows, loaded once per batch and shared read-only.",
    )
    skipped: bool = Field(
        default=False, description="True if the invoice was skipped (unreadable/empty PDF)."
    )
    skip_reason: str = Field(default="", description="Why the invoice was skipped.")
    errored: bool = Field(
        default=False, description="True if a processing stage failed."
    )
    error_reason: str = Field(default="", description="Why processing errored.")
    extracted: ExtractedInvoice | None = Field(
        default=None, description="Structured extraction result."
    )
    verification: VerificationResult | None = Field(
        default=None, description="Arithmetic verification result."
    )
    categorized: CategorizedInvoice | None = Field(
        default=None, description="Final categorization result."
    )
    categorization_note: str = Field(
        default="", description="Note about grounding/snapping during categorization."
    )
