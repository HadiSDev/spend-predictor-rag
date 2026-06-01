"""Pydantic data models for the invoice pipeline and flow state."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    amount: float


class ExtractedInvoice(BaseModel):
    vendor_name: str
    invoice_number: str | None = None
    invoice_date: str | None = None  # ISO if parseable, else raw
    currency: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float


class VerificationResult(BaseModel):
    arithmetic_ok: bool
    discrepancies: list[str] = Field(default_factory=list)
    notes: str | None = None


class CategorizedInvoice(BaseModel):
    account_code: str
    account_name: str
    category: str
    confidence: float  # 0..1
    rationale: str


class InvoiceState(BaseModel):
    """Flow state for processing a single invoice."""

    pdf_path: str = ""
    invoice_text: str = ""
    skipped: bool = False
    skip_reason: str = ""
    errored: bool = False
    error_reason: str = ""
    extracted: ExtractedInvoice | None = None
    verification: VerificationResult | None = None
    categorized: CategorizedInvoice | None = None
    categorization_note: str = ""
