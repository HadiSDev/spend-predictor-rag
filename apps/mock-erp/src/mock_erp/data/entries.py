"""GL entry (ledger posting) generation for the mock ERP."""

from __future__ import annotations

import itertools

from .accounts import account_name
from .seeding import seeded_random

_VAT_INPUT_ACCOUNT = 2200
_ACCOUNTS_PAYABLE = 2100
_CASH_ACCOUNT = 1000


def generate(invoices: list[dict], seed: int = 42) -> list[dict]:
    """Generate GL entries reconciling with ``invoices`` plus some unlinked ones."""
    rng = seeded_random(seed)
    entries: list[dict] = []
    entry_numbers = itertools.count(9001)

    def _emit(voucher: int, account: int, debit: float, credit: float,
              d: str, currency: str, entry_type: str, description: str,
              line_number: int | None = None) -> None:
        entries.append({
            "entryNumber": next(entry_numbers),
            "voucherId": voucher,
            "entryType": entry_type,
            "account": {"accountNumber": account, "name": account_name(account)},
            "date": d,
            "description": description,
            "debit": round(debit, 2),
            "credit": round(credit, 2),
            "currency": currency,
            "lineNumber": line_number,
        })

    for inv in invoices:
        voucher = inv["voucherId"]
        d = inv["date"]
        currency = inv.get("currency", "DKK")
        vendor_name = inv.get("supplier", {}).get("name", "")

        for ln in inv.get("lines", []):
            acct = ln.get("account", {}).get("accountNumber")
            if acct is None:
                continue
            _emit(voucher, acct, debit=ln.get("netAmount", 0.0), credit=0.0, d=d,
                  currency=currency, entry_type="purchase_invoice",
                  description=ln.get("description") or f"{vendor_name} — {account_name(acct)}",
                  line_number=ln.get("lineNumber"))

        vat = inv.get("vatAmount", 0.0)
        if vat:
            _emit(voucher, _VAT_INPUT_ACCOUNT, debit=vat, credit=0.0, d=d,
                  currency=currency, entry_type="purchase_invoice",
                  description=f"{vendor_name} — input VAT")

        gross = inv.get("grossAmount", 0.0)
        _emit(voucher, _ACCOUNTS_PAYABLE, debit=0.0, credit=gross, d=d,
              currency=currency, entry_type="purchase_invoice",
              description=f"{vendor_name} — payable")

    payment_vouchers = itertools.count(8001)
    for inv in invoices:
        if rng.random() < 0.3:
            v = next(payment_vouchers)
            gross = inv.get("grossAmount", 0.0)
            d = inv["date"]
            currency = inv.get("currency", "DKK")
            _emit(v, _ACCOUNTS_PAYABLE, debit=gross, credit=0.0, d=d,
                  currency=currency, entry_type="payment",
                  description="Supplier payment — clear payable")
            _emit(v, _CASH_ACCOUNT, debit=0.0, credit=gross, d=d,
                  currency=currency, entry_type="payment",
                  description="Supplier payment — cash out")

    return entries
