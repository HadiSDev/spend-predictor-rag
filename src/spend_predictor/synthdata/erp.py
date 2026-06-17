"""Build a balanced double-entry journal for a synthetic invoice (AP booking)."""
from __future__ import annotations

from dataclasses import dataclass

from ..models import ExtractedInvoice

AP_CODE, AP_NAME = "2000", "Accounts Payable"
VAT_INPUT_CODE, VAT_INPUT_NAME = "1300", "VAT Input (Receivable)"


@dataclass
class JournalEntry:
    account_code: str
    account_name: str
    debit: float
    credit: float


def build_journal(
    invoice: ExtractedInvoice, account_code: str, account_name: str
) -> list[JournalEntry]:
    """Dr expense (net) + Dr VAT input (tax) ... Cr accounts payable (total)."""
    net = round(invoice.subtotal or 0.0, 2)
    tax = round(invoice.tax or 0.0, 2)
    total = round(invoice.total, 2)
    entries = [JournalEntry(account_code, account_name, debit=net, credit=0.0)]
    if tax > 0:
        entries.append(JournalEntry(VAT_INPUT_CODE, VAT_INPUT_NAME, debit=tax, credit=0.0))
    entries.append(JournalEntry(AP_CODE, AP_NAME, debit=0.0, credit=total))
    return entries
