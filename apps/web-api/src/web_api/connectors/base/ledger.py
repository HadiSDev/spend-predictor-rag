"""Normalized chart-of-accounts and ledger postings from an ERP."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ErpAccountData(BaseModel):
    erp_account_code: str
    erp_account_name: str
    erp_account_type: str | None = None
    parent_code: str | None = None
    is_active: bool = True
    with_vat: bool = False
    raw: dict = {}


class ErpEntryData(BaseModel):
    """A normalized GL posting (ledger entry) from an ERP."""

    erp_entry_id: str
    voucher_id: str
    entry_type: str
    erp_account_code: str
    source_line_erp_id: str | None = None
    accounting_date: date | None = None
    description: str | None = None
    debit_amount: float | None = None
    credit_amount: float | None = None
    currency: str | None = None
    raw: dict = {}
