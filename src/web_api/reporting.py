"""Read-only aggregate reporting over the domain tables.

Pure SQL `GROUP BY` rollups the customer API exposes under `/api/v1/reports/*`.
Each function takes an explicit, already-scoped `company_ids` list (the router
resolves it from the caller's tenant scope) and returns a list of plain row
dicts; the router maps those onto response schemas.

Money is always grouped by a currency column — amounts of different currencies
are never summed together — and sums are coalesced to 0 so a group is never null.
Ledger sums come from `ErpEntry` (the financial source of truth); category and
vendor spend come from the invoice/line layer, where those dimensions live.

**Which** currency column depends on the mode. `base` (the default) groups by the
stored `base_currency` and sums the converted amounts, so a customer sees one
figure per dimension in their own currency. `original` groups by the as-posted
`currency` and reproduces the pre-conversion behaviour exactly.

Rows that could not be converted have a null `base_currency`, so in base mode
they form their own group: currency null, totals 0, and `unconverted_count` set.
That is deliberate — money we cannot express in the customer's currency is
reported as its own visible line rather than folded into a total it does not
belong in, or dropped so the total silently understates spend.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import Session, select

from .db.models import ErpAccount, ErpEntry, Invoice, InvoiceLine, Vendor
from .db.models.enums import LineStatus

_ZERO = Decimal("0")


def _dec(value) -> Decimal:
    """Coalesce a possibly-None SQL sum to a Decimal 0."""
    return Decimal(str(value)) if value is not None else _ZERO


BASE = "base"
ORIGINAL = "original"


def _entry_columns(mode: str):
    """`(currency, debit, credit)` columns for an ErpEntry rollup."""
    if mode == BASE:
        return ErpEntry.base_currency, ErpEntry.base_debit_amount, ErpEntry.base_credit_amount
    return ErpEntry.currency, ErpEntry.debit_amount, ErpEntry.credit_amount


def _unconverted(mode: str, currency, count: int) -> int:
    """How many rows in this group had no base amount.

    A null currency in base mode *is* the unconverted group — the base columns
    are only ever null together — so the group's own count is the answer. In
    original mode nothing is excluded, so it is always zero (a null posted
    currency there is just an ERP that did not say).
    """
    return count if mode == BASE and currency is None else 0


def entries_summary(
    session: Session,
    company_ids: list[str],
    *,
    entry_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    currency_mode: str = BASE,
) -> list[dict]:
    """Sum debits/credits (+ net, count) per `(entry_type, currency)`."""
    if not company_ids:
        return []
    currency_col, debit_col, credit_col = _entry_columns(currency_mode)
    debit = func.coalesce(func.sum(debit_col), 0)
    credit = func.coalesce(func.sum(credit_col), 0)
    conditions = [ErpEntry.company_id.in_(company_ids)]
    if entry_type is not None:
        conditions.append(ErpEntry.entry_type == entry_type)
    if from_date is not None:
        conditions.append(ErpEntry.accounting_date >= from_date)
    if to_date is not None:
        conditions.append(ErpEntry.accounting_date <= to_date)

    rows = session.exec(
        select(ErpEntry.entry_type, currency_col, debit, credit, func.count())
        .where(*conditions)
        .group_by(ErpEntry.entry_type, currency_col)
    ).all()
    result = [
        {
            "entry_type": et,
            "currency": cur,
            "debit_total": _dec(deb),
            "credit_total": _dec(cred),
            "net": _dec(deb) - _dec(cred),
            "count": cnt,
            "unconverted_count": _unconverted(currency_mode, cur, cnt),
        }
        for et, cur, deb, cred, cnt in rows
    ]
    result.sort(key=lambda r: (-r["debit_total"], r["entry_type"] or "", r["currency"] or ""))
    return result


def entries_by_account(
    session: Session,
    company_ids: list[str],
    *,
    entry_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    currency_mode: str = BASE,
) -> list[dict]:
    """Sum debits/credits (+ net, count) per ERP account and currency."""
    if not company_ids:
        return []
    currency_col, debit_col, credit_col = _entry_columns(currency_mode)
    debit = func.coalesce(func.sum(debit_col), 0)
    credit = func.coalesce(func.sum(credit_col), 0)
    conditions = [ErpEntry.company_id.in_(company_ids)]
    if entry_type is not None:
        conditions.append(ErpEntry.entry_type == entry_type)
    if from_date is not None:
        conditions.append(ErpEntry.accounting_date >= from_date)
    if to_date is not None:
        conditions.append(ErpEntry.accounting_date <= to_date)

    rows = session.exec(
        select(
            ErpAccount.id, ErpAccount.erp_account_code, ErpAccount.erp_account_name,
            currency_col, debit, credit, func.count(),
        )
        .join(ErpAccount, ErpEntry.erp_account_id == ErpAccount.id)
        .where(*conditions)
        .group_by(ErpAccount.id, ErpAccount.erp_account_code,
                  ErpAccount.erp_account_name, currency_col)
    ).all()
    result = [
        {
            "erp_account_id": aid,
            "erp_account_code": code,
            "erp_account_name": name,
            "currency": cur,
            "debit_total": _dec(deb),
            "credit_total": _dec(cred),
            "net": _dec(deb) - _dec(cred),
            "count": cnt,
            "unconverted_count": _unconverted(currency_mode, cur, cnt),
        }
        for aid, code, name, cur, deb, cred, cnt in rows
    ]
    result.sort(key=lambda r: (-r["debit_total"], r["erp_account_code"] or "", r["currency"] or ""))
    return result


def spend_by_category(
    session: Session,
    company_ids: list[str],
    *,
    level: str = "level_2",
    from_date: date | None = None,
    to_date: date | None = None,
    currency_mode: str = BASE,
) -> list[dict]:
    """Sum categorized invoice-line amounts + count per spend level and currency.

    Only `ai_categorized`/`verified` lines count. ``level`` is ``level_2``
    (default) or ``level_3`` — the latter groups by both level_2 and level_3.
    The date filter comes from the parent invoice; so does the posted currency,
    while the base currency is stamped on the line by its own conversion.
    """
    if not company_ids:
        return []
    by_l3 = level == "level_3"
    if currency_mode == BASE:
        currency_col, amount_col = InvoiceLine.base_currency, InvoiceLine.base_amount
    else:
        currency_col, amount_col = Invoice.currency, InvoiceLine.amount
    amount = func.coalesce(func.sum(amount_col), 0)
    conditions = [
        InvoiceLine.company_id.in_(company_ids),
        InvoiceLine.status.in_([LineStatus.AI_CATEGORIZED, LineStatus.VERIFIED]),
    ]
    if from_date is not None:
        conditions.append(Invoice.invoice_date >= from_date)
    if to_date is not None:
        conditions.append(Invoice.invoice_date <= to_date)

    dims = [InvoiceLine.level_2, InvoiceLine.level_3] if by_l3 else [InvoiceLine.level_2]
    group_cols = [*dims, currency_col]

    rows = session.exec(
        select(*dims, currency_col, amount, func.count())
        .join(Invoice, InvoiceLine.invoice_id == Invoice.id)
        .where(*conditions)
        .group_by(*group_cols)
    ).all()
    result = []
    for row in rows:
        if by_l3:
            l2, l3, cur, amt, cnt = row
        else:
            l2, cur, amt, cnt = row
            l3 = None
        result.append({
            "level_2": l2,
            "level_3": l3,
            "currency": cur,
            "amount_total": _dec(amt),
            "count": cnt,
            "unconverted_count": _unconverted(currency_mode, cur, cnt),
        })
    result.sort(key=lambda r: (-r["amount_total"], r["level_2"] or "", r["level_3"] or "", r["currency"] or ""))
    return result


def spend_by_vendor(
    session: Session,
    company_ids: list[str],
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    currency_mode: str = BASE,
) -> list[dict]:
    """Sum invoice totals + count per vendor and currency."""
    if not company_ids:
        return []
    if currency_mode == BASE:
        currency_col, amount_col = Invoice.base_currency, Invoice.base_total
    else:
        currency_col, amount_col = Invoice.currency, Invoice.total
    amount = func.coalesce(func.sum(amount_col), 0)
    conditions = [Invoice.company_id.in_(company_ids)]
    if from_date is not None:
        conditions.append(Invoice.invoice_date >= from_date)
    if to_date is not None:
        conditions.append(Invoice.invoice_date <= to_date)

    rows = session.exec(
        select(Vendor.id, Vendor.name, currency_col, amount, func.count())
        .join(Vendor, Invoice.vendor_id == Vendor.id)
        .where(*conditions)
        .group_by(Vendor.id, Vendor.name, currency_col)
    ).all()
    result = [
        {
            "vendor_id": vid,
            "vendor_name": vname,
            "currency": cur,
            "amount_total": _dec(amt),
            "count": cnt,
            "unconverted_count": _unconverted(currency_mode, cur, cnt),
        }
        for vid, vname, cur, amt, cnt in rows
    ]
    result.sort(key=lambda r: (-r["amount_total"], r["vendor_name"] or "", r["currency"] or ""))
    return result
