"""Pydantic data models for the invoice pipeline and flow state."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = Field(
        description="Free-text description of the product or service on this line."
    )
    quantity: float | None = Field(
        default=None, description="Quantity billed on this line, if stated."
    )
    unit_type: str | None = Field(
        default=None,
        description="Unit of measure for the quantity, e.g. 'hours', 'pcs', 'kg', 'months'.",
    )
    unit_price: float | None = Field(
        default=None, description="Price per unit, excluding VAT, if stated."
    )
    amount: float = Field(
        description="Net line amount (quantity x unit_price), excluding VAT."
    )
    vat_code: str | None = Field(
        default=None,
        description="VAT category code for the line, e.g. 'S' standard, 'R' reduced, "
        "'Z' zero-rated, 'E' exempt.",
    )
    vat_rate: float | None = Field(
        default=None,
        description="VAT rate applied to the line, as a percentage (e.g. 25.0 for 25%).",
    )


class ExtractedInvoice(BaseModel):
    vendor_name: str = Field(description="Supplier (seller) company name.")
    supplier_country_code: str | None = Field(
        default=None,
        description="Supplier country as an ISO 3166-1 alpha-2 code, e.g. 'DK', 'DE', 'US'.",
    )
    supplier_vat_number: str | None = Field(
        default=None,
        description="Supplier company VAT registration number, e.g. 'DK12345678'.",
    )
    buyer_country_code: str | None = Field(
        default=None,
        description="Buyer country as an ISO 3166-1 alpha-2 code, read from the "
        "invoice bill-to block.",
    )
    buyer_vat_number: str | None = Field(
        default=None,
        description="Buyer company VAT registration number, read from the invoice "
        "bill-to block.",
    )
    invoice_number: str | None = Field(
        default=None, description="Invoice number / identifier as printed."
    )
    invoice_date: str | None = Field(
        default=None,
        description="Invoice date; ISO 8601 (YYYY-MM-DD) if parseable, else the raw string.",
    )
    currency: str | None = Field(
        default=None, description="ISO 4217 currency code, e.g. 'USD', 'EUR', 'DKK'."
    )
    line_items: list[LineItem] = Field(
        default_factory=list, description="The invoice line items."
    )
    subtotal: float | None = Field(
        default=None, description="Net total of all line items, excluding VAT."
    )
    tax: float | None = Field(
        default=None, description="Total VAT amount across the invoice."
    )
    total: float = Field(
        description="Gross invoice total, including VAT (subtotal + tax)."
    )


class VerificationResult(BaseModel):
    arithmetic_ok: bool = Field(
        description="True if the invoice arithmetic reconciles (lines -> subtotal, "
        "subtotal + tax -> total)."
    )
    discrepancies: list[str] = Field(
        default_factory=list,
        description="Human-readable description of each arithmetic discrepancy found.",
    )
    notes: str | None = Field(
        default=None, description="Optional free-text notes from the verification."
    )


class AccountChoice(BaseModel):
    """Categorizer output: the chosen leaf account + the buyer-derived L1."""

    account_code: str = Field(
        description="Chosen leaf account code, copied exactly from the candidate list."
    )
    account_name: str = Field(
        description="Chosen leaf account name, matching account_code."
    )
    level1: Literal["Direct", "Indirect"] = Field(
        description="Spend class derived from the buyer's business: 'Direct' (cost of "
        "revenue) or 'Indirect' (overhead)."
    )
    confidence: float = Field(
        description="Confidence in the categorization, from 0.0 to 1.0."
    )
    rationale: str = Field(
        description="Brief justification for the account and Direct/Indirect choice."
    )


class CategorizedInvoice(BaseModel):
    """Final, hierarchy-enriched categorization (L2/L3/leaf from the chart)."""

    account_code: str = Field(description="Leaf account code from the chart of accounts.")
    account_name: str = Field(description="Leaf account name from the chart of accounts.")
    level1: str = Field(description="Direct or Indirect, from the model (buyer-derived).")
    level2: str = Field(description="Level-2 category from the chart of accounts.")
    level3: str = Field(description="Level-3 subcategory from the chart of accounts.")
    confidence: float = Field(
        description="Confidence in the categorization, from 0.0 to 1.0."
    )
    rationale: str = Field(description="Brief justification for the categorization.")


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
