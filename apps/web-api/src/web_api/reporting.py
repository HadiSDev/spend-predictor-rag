"""Read-only aggregate reporting over the domain tables."""
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
    """How many rows in this group had no base amount."""
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


_LEVEL_COLUMNS = ("level_1", "level_2", "level_3", "level_4")
_LEVEL_DEPTH = {name: index + 1 for index, name in enumerate(_LEVEL_COLUMNS)}


def spend_by_category(
    session: Session,
    company_ids: list[str],
    *,
    level: str = "level_2",
    from_date: date | None = None,
    to_date: date | None = None,
    currency_mode: str = BASE,
) -> list[dict]:
    """Sum categorized invoice-line amounts + count per spend level and currency."""
    if not company_ids:
        return []
    depth = _LEVEL_DEPTH.get(level)
    if depth is None:
        raise ValueError(f"unknown spend level {level!r}")
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

    dims = [getattr(InvoiceLine, name) for name in _LEVEL_COLUMNS[:depth]]
    group_cols = [*dims, currency_col]

    rows = session.exec(
        select(*dims, currency_col, amount, func.count())
        .join(Invoice, InvoiceLine.invoice_id == Invoice.id)
        .where(*conditions)
        .group_by(*group_cols)
    ).all()
    result = []
    for row in rows:
        *levels, cur, amt, cnt = row
        entry = {name: None for name in _LEVEL_COLUMNS}
        entry.update(dict(zip(_LEVEL_COLUMNS, levels)))
        entry.update({
            "currency": cur,
            "amount_total": _dec(amt),
            "count": cnt,
            "unconverted_count": _unconverted(currency_mode, cur, cnt),
        })
        result.append(entry)
    result.sort(key=lambda r: (
        -r["amount_total"],
        *(r[name] or "" for name in _LEVEL_COLUMNS),
        r["currency"] or "",
    ))
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
