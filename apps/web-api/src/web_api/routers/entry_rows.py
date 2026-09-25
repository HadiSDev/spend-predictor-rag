"""Named result rows for the ERP entry queries."""
from __future__ import annotations

from typing import NamedTuple

from web_api.db.models import ErpEntry


class EntryRow(NamedTuple):
    """One posting with its account, vendor and spend category columns."""

    entry: ErpEntry
    account_code: str
    account_name: str
    vendor_id: str | None
    vendor_name: str | None
    account_type: str | None
    level_1: str | None
    level_2: str | None
    level_3: str | None


class InvoiceHeaderState(NamedTuple):
    """The document and header fields a voucher group shows for its invoice."""

    doc_status: str
    doc_error: str | None
    invoice_number: str | None
    document_invoice_number: str | None
