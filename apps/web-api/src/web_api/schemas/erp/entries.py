"""Raw ERP postings and the vouchers they make up."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from ..invoices.invoice import DocumentRead, InvoiceDetailRead
from ..invoices.lines import InvoiceLineRead


class ErpEntryRead(BaseModel):
    """A raw GL entry (posting)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    erp_account_id: str
    source_invoice_id: str | None = None
    voucher_id: str | None = None
    voucher_number: str | None = None
    entry_type: str
    accounting_date: date | None = None
    description: str | None = None
    debit_amount: Decimal | None = None
    credit_amount: Decimal | None = None
    currency: str | None = None
    erp_entry_id: str | None = None
    base_currency: str | None = None
    base_debit_amount: Decimal | None = None
    base_credit_amount: Decimal | None = None
    fx_rate: Decimal | None = None
    fx_rate_date: date | None = None
    status: str
    error_message: str | None = None
    created_at: datetime

    erp_account_code: str
    erp_account_name: str
    erp_account_type: str | None = None
    vendor_id: str | None = None
    vendor_name: str | None = None

    source_invoice_line_id: str | None = None
    spend_category_level_1: str | None = None
    spend_category_level_2: str | None = None
    spend_category_level_3: str | None = None


class VoucherGroupRead(BaseModel):
    """The postings that make up one spend event."""

    voucher_id: str | None = None
    voucher_number: str | None = None
    company_id: str
    accounting_date: date | None = None
    entry_types: list[str] = []
    entry_count: int
    amount: Decimal | None = None
    debit_total: Decimal | None = None
    credit_total: Decimal | None = None
    currency: str | None = None
    unconverted_count: int = 0
    vendor_id: str | None = None
    vendor_name: str | None = None
    entries: list[ErpEntryRead] = []
    lines: list[InvoiceLineRead] = []
    doc_status: str | None = None
    doc_error: str | None = None
    invoice_number: str | None = None
    document_invoice_number: str | None = None


class VoucherDetailRead(BaseModel):
    """Everything one voucher's detail panel needs, in one request."""

    voucher_id: str | None = None
    voucher_number: str | None = None
    company_id: str
    accounting_date: date | None = None
    currency: str | None = None
    amount: Decimal | None = None
    entry_count: int
    entries: list[ErpEntryRead] = []
    invoice: InvoiceDetailRead | None = None
    document: DocumentRead | None = None
