"""Invoices as read, with their lines and document."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from ..invoices.lines import InvoiceLineRead


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    vendor_id: str | None = None
    invoice_number: str | None = None
    document_invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    total: Decimal | None = None
    tax: Decimal | None = None
    base_currency: str | None = None
    base_total: Decimal | None = None
    base_tax: Decimal | None = None
    fx_rate: Decimal | None = None
    fx_rate_date: date | None = None
    supplier_name: str | None = None
    supplier_country_code: str | None = None
    supplier_vat_number: str | None = None
    supplier_overrides: list[str] = []
    status: str
    source: str = "erp"
    verified_fields: list[str] = []
    verified_at: datetime | None = None
    verified_by: str | None = None
    error_message: str | None = None
    file_id: str | None = None
    file_name: str | None = None
    has_document: bool = False
    doc_status: str = "not_applicable"
    doc_error: str | None = None
    doc_processed_at: datetime | None = None

    document_total: Decimal | None = None
    document_tax: Decimal | None = None
    totals_agree: bool | None = None


class InvoiceDetailRead(InvoiceRead):
    lines: list[InvoiceLineRead] = []
    lines_reconciled: bool = True
    reconciliation_delta: Decimal | None = None


class DocumentRead(BaseModel):
    """The document attached to a voucher's invoice."""

    file_id: str
    filename: str
