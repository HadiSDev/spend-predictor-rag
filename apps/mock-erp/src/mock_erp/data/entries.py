"""GL entry (ledger posting) generation for the mock ERP.

Real ERPs expose the ledger as **entries** — individual debit/credit postings —
not as invoices. Each entry carries the ``voucherId`` of the posting it belongs
to. One posted purchase invoice becomes several entries — **one debit per invoice
line**, carrying that line's description, plus an input-VAT debit and an
accounts-payable credit — that reconcile to the invoice's net + VAT. Some
vouchers (payments, journal entries) have no invoice scan at all — they exist to
prove that entries can be unlinked.

Entries are derived from the already-generated invoices so the two datasets stay
mutually reconcilable.
"""

from __future__ import annotations

import hashlib
import random

# Standard postings-side accounts (present in the mock chart of accounts).
_VAT_INPUT_ACCOUNT = 2200  # VAT Payable (used here as input VAT for simplicity)
_ACCOUNTS_PAYABLE = 2100
_CASH_ACCOUNT = 1000


def _seeded_random(seed: int | str) -> random.Random:
    if isinstance(seed, str):
        seed = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    return random.Random(seed)


def _account_name(account_number: int) -> str:
    from .accounts import ACCOUNTS

    for a in ACCOUNTS:
        if a["accountNumber"] == account_number:
            return a["name"]
    return "Unknown"


def generate(invoices: list[dict], seed: int = 42) -> list[dict]:
    """Generate GL entries reconciling with ``invoices`` plus some unlinked ones.

    Returns a list of entry dicts matching the ``/api/v1/entries`` schema. Each
    entry has an ``entryType`` of ``purchase_invoice`` | ``payment`` |
    ``journal_entry``. Only ``purchase_invoice`` entries share a voucher with an
    invoice scan.
    """
    rng = _seeded_random(seed)
    entries: list[dict] = []
    entry_no = [9000]

    def _emit(voucher: int, account: int, debit: float, credit: float,
              d: str, currency: str, entry_type: str, description: str,
              line_number: int | None = None) -> None:
        entry_no[0] += 1
        entries.append({
            "entryNumber": entry_no[0],
            "voucherId": voucher,
            "entryType": entry_type,
            "account": {"accountNumber": account, "name": _account_name(account)},
            "date": d,
            "description": description,
            "debit": round(debit, 2),
            "credit": round(credit, 2),
            "currency": currency,
            # The invoice line this posting came from, when there is one. Input
            # VAT and the payable are properties of the whole invoice, so they
            # carry none — and a consumer must not read that as a defect.
            "lineNumber": line_number,
        })

    for inv in invoices:
        voucher = inv["voucherId"]
        d = inv["date"]
        currency = inv.get("currency", "DKK")
        vendor_name = inv.get("supplier", {}).get("name", "")

        # One debit posting per invoice line, carrying that line's own text.
        #
        # This is what a real ERP does, and the text is the point: an expense
        # posting's description is the line it came from, which is what lets a
        # ledger row be read against the invoice and tied back to the
        # `InvoiceLine` the categorizer worked on. Netting the lines per account
        # — the earlier shape — threw that text away and, since every line of an
        # invoice shares one account here, collapsed each invoice to a single
        # anonymous "Vendor — Account name" posting.
        for ln in inv.get("lines", []):
            acct = ln.get("account", {}).get("accountNumber")
            if acct is None:
                continue
            _emit(voucher, acct, debit=ln.get("netAmount", 0.0), credit=0.0, d=d,
                  currency=currency, entry_type="purchase_invoice",
                  # A line without text still has to say something a human can
                  # read, so fall back to the account it posted to.
                  description=ln.get("description") or f"{vendor_name} — {_account_name(acct)}",
                  line_number=ln.get("lineNumber"))

        # Input VAT debit.
        vat = inv.get("vatAmount", 0.0)
        if vat:
            _emit(voucher, _VAT_INPUT_ACCOUNT, debit=vat, credit=0.0, d=d,
                  currency=currency, entry_type="purchase_invoice",
                  description=f"{vendor_name} — input VAT")

        # Accounts-payable credit for the gross (balances the voucher).
        gross = inv.get("grossAmount", 0.0)
        _emit(voucher, _ACCOUNTS_PAYABLE, debit=0.0, credit=gross, d=d,
              currency=currency, entry_type="purchase_invoice",
              description=f"{vendor_name} — payable")

    # A handful of non-invoice vouchers (payments settling some invoices, and a
    # standalone journal entry). These carry vouchers with NO invoice scan, so an
    # importer must leave their source_invoice link empty.
    payment_voucher = [8000]
    for inv in invoices:
        if rng.random() < 0.3:  # ~30% of invoices get a payment voucher
            payment_voucher[0] += 1
            v = payment_voucher[0]
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
