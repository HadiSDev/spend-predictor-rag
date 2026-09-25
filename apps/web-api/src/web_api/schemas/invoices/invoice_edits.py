"""Corrections to a parsed invoice header."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class InvoiceUpdate(BaseModel):
    """Corrections to a parsed invoice header."""

    document_invoice_number: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    total: Decimal | None = None
    tax: Decimal | None = None
    vendor_id: str | None = None
    supplier_name: str | None = None
    supplier_country_code: str | None = Field(default=None, max_length=2)
    supplier_vat_number: str | None = None


class InvoiceVerify(InvoiceUpdate):
    """Verify an invoice header, optionally correcting it first."""
