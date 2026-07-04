"""Read-only aggregate reporting over the domain tables.

Pure SQL `GROUP BY` rollups the customer API exposes under `/api/v1/reports/*`.
Each function takes an explicit, already-scoped `company_ids` list (the router
resolves it from the caller's tenant scope) and returns a list of plain row
dicts; the router maps those onto response schemas.

Money is always grouped by `currency` — amounts of different currencies are
never summed together — and sums are coalesced to 0 so a group is never null.
Ledger sums come from `ErpEntry` (the financial source of truth); category and
vendor spend come from the invoice/line layer, where those dimensions live.
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


def entries_summary(
    session: Session,
    company_ids: list[str],
    *,
    entry_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    """Sum debits/credits (+ net, count) per `(entry_type, currency)`."""
    if not company_ids:
        return []
    debit = func.coalesce(func.sum(ErpEntry.debit_amount), 0)
    credit = func.coalesce(func.sum(ErpEntry.credit_amount), 0)
    conditions = [ErpEntry.company_id.in_(company_ids)]
    if entry_type is not None:
        conditions.append(ErpEntry.entry_type == entry_type)
    if from_date is not None:
        conditions.append(ErpEntry.accounting_date >= from_date)
    if to_date is not None:
        conditions.append(ErpEntry.accounting_date <= to_date)

    rows = session.exec(
        select(ErpEntry.entry_type, ErpEntry.currency, debit, credit, func.count())
        .where(*conditions)
        .group_by(ErpEntry.entry_type, ErpEntry.currency)
    ).all()
    result = [
        {
            "entry_type": et,
            "currency": cur,
            "debit_total": _dec(deb),
            "credit_total": _dec(cred),
            "net": _dec(deb) - _dec(cred),
            "count": cnt,
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
) -> list[dict]:
    """Sum debits/credits (+ net, count) per ERP account and currency."""
    if not company_ids:
        return []
    debit = func.coalesce(func.sum(ErpEntry.debit_amount), 0)
    credit = func.coalesce(func.sum(ErpEntry.credit_amount), 0)
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
            ErpEntry.currency, debit, credit, func.count(),
        )
        .join(ErpAccount, ErpEntry.erp_account_id == ErpAccount.id)
        .where(*conditions)
        .group_by(ErpAccount.id, ErpAccount.erp_account_code,
                  ErpAccount.erp_account_name, ErpEntry.currency)
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
) -> list[dict]:
    """Sum categorized invoice-line amounts + count per spend level and currency.

    Only `ai_categorized`/`verified` lines count. ``level`` is ``level_2``
    (default) or ``level_3`` — the latter groups by both level_2 and level_3.
    Currency and the date filter come from the parent invoice.
    """
    if not company_ids:
        return []
    by_l3 = level == "level_3"
    amount = func.coalesce(func.sum(InvoiceLine.amount), 0)
    conditions = [
        InvoiceLine.company_id.in_(company_ids),
        InvoiceLine.status.in_([LineStatus.AI_CATEGORIZED, LineStatus.VERIFIED]),
    ]
    if from_date is not None:
        conditions.append(Invoice.invoice_date >= from_date)
    if to_date is not None:
        conditions.append(Invoice.invoice_date <= to_date)

    dims = [InvoiceLine.level_2, InvoiceLine.level_3] if by_l3 else [InvoiceLine.level_2]
    group_cols = [*dims, Invoice.currency]

    rows = session.exec(
        select(*dims, Invoice.currency, amount, func.count())
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
        })
    result.sort(key=lambda r: (-r["amount_total"], r["level_2"] or "", r["level_3"] or "", r["currency"] or ""))
    return result


def spend_by_vendor(
    session: Session,
    company_ids: list[str],
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    """Sum invoice totals + count per vendor and currency."""
    if not company_ids:
        return []
    amount = func.coalesce(func.sum(Invoice.total), 0)
    conditions = [Invoice.company_id.in_(company_ids)]
    if from_date is not None:
        conditions.append(Invoice.invoice_date >= from_date)
    if to_date is not None:
        conditions.append(Invoice.invoice_date <= to_date)

    rows = session.exec(
        select(Vendor.id, Vendor.name, Invoice.currency, amount, func.count())
        .join(Vendor, Invoice.vendor_id == Vendor.id)
        .where(*conditions)
        .group_by(Vendor.id, Vendor.name, Invoice.currency)
    ).all()
    result = [
        {
            "vendor_id": vid,
            "vendor_name": vname,
            "currency": cur,
            "amount_total": _dec(amt),
            "count": cnt,
        }
        for vid, vname, cur, amt, cnt in rows
    ]
    result.sort(key=lambda r: (-r["amount_total"], r["vendor_name"] or "", r["currency"] or ""))
    return result
