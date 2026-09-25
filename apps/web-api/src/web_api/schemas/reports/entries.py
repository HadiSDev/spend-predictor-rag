"""Report rows aggregated over ERP postings."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class EntrySummaryRow(BaseModel):
    entry_type: str
    currency: str | None = None
    debit_total: Decimal
    credit_total: Decimal
    net: Decimal
    count: int
    unconverted_count: int = 0


class EntryAccountRow(BaseModel):
    erp_account_id: str
    erp_account_code: str
    erp_account_name: str
    currency: str | None = None
    debit_total: Decimal
    credit_total: Decimal
    net: Decimal
    count: int
    unconverted_count: int = 0
