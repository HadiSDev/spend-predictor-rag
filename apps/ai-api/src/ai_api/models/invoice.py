"""Invoice data as extracted from a document, and its arithmetic check."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    item_name: str | None = Field(
        default=None,
        description="The name of the product or service on this line, as the "
        "document names it — just the thing bought, with no quantity, price, "
        "date or contract term folded in.",
    )
    description: str | None = Field(
        default=None,
        description="Any further prose this line printed beyond its name — "
        "terms, period covered, specification. Null when the line printed none.",
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
    amount: float | None = Field(
        default=None,
        description="The line's total in money, exactly as the document's amount "
        "column states it — VAT-inclusive or not, whichever the document prints.",
    )
    subtotal: float | None = Field(
        default=None,
        description="The line's amount NET of VAT, when the document prints a "
        "net figure separately from a gross one. Null when it prints only one.",
    )
    tax_amount: float | None = Field(
        default=None,
        description="The VAT charged on this line in money, if the line states it.",
    )
    discount: float | None = Field(
        default=None,
        description="A discount stated on this line, as a money amount. Record it "
        "as its own figure; do not subtract it from the line's total.",
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
    total: float | None = Field(
        default=None,
        description="Gross invoice total, including VAT (subtotal + tax), as the "
        "document states it. Null when the document states no total at all.",
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
