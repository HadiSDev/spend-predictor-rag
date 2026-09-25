"""Normalized vendors and purchase invoices from an ERP."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ErpVendorData(BaseModel):
    erp_id: str
    name: str
    country_code: str | None = None
    vat_number: str | None = None
    description: str | None = None
    raw: dict = {}


class ErpInvoiceLineData(BaseModel):
    line_erp_id: str | None = None
    item_name: str | None = None
    description: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    amount: float
    native_account_code: str | None = None
    raw: dict = {}


class ErpInvoiceData(BaseModel):
    erp_id: str
    vendor_erp_id: str
    vendor_name: str
    invoice_number: str | None = None
    invoice_date: date
    currency: str
    total: float
    tax: float | None = None
    voucher_id: str | None = None
    file_name: str | None = None
    file_ref: str | None = None
    lines: list[ErpInvoiceLineData] = []
    raw: dict = {}
