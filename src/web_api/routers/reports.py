"""Aggregate reporting endpoints — read-only, tenant-scoped, grouped by currency.

Ledger sums come from `ErpEntry`; category/vendor spend from the invoice layer.
All endpoints resolve the caller's company scope (optionally narrowed by a
validated `company_id`) and delegate the SQL rollups to `web_api.reporting`.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from .. import reporting
from ..deps import TenantScope, get_session, resolve_company_ids, tenant_scope
from ..schemas import (
    CategorySpendRow,
    CurrencyMode,
    EntryAccountRow,
    EntrySummaryRow,
    Report,
    VendorSpendRow,
)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/entries-summary", response_model=Report[EntrySummaryRow])
def entries_summary(
    company_id: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    currency_mode: CurrencyMode = Query(default="base"),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Report:
    company_ids = resolve_company_ids(scope, company_id)
    rows = reporting.entries_summary(
        session, company_ids, entry_type=entry_type, from_date=from_date, to_date=to_date,
        currency_mode=currency_mode,
    )
    return Report(rows=rows)


@router.get("/entries-by-account", response_model=Report[EntryAccountRow])
def entries_by_account(
    company_id: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    currency_mode: CurrencyMode = Query(default="base"),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Report:
    company_ids = resolve_company_ids(scope, company_id)
    rows = reporting.entries_by_account(
        session, company_ids, entry_type=entry_type, from_date=from_date, to_date=to_date,
        currency_mode=currency_mode,
    )
    return Report(rows=rows)


@router.get("/spend-by-category", response_model=Report[CategorySpendRow])
def spend_by_category(
    company_id: str | None = Query(default=None),
    level: str = Query(default="level_2", pattern="^(level_2|level_3)$"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    currency_mode: CurrencyMode = Query(default="base"),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Report:
    company_ids = resolve_company_ids(scope, company_id)
    rows = reporting.spend_by_category(
        session, company_ids, level=level, from_date=from_date, to_date=to_date,
        currency_mode=currency_mode,
    )
    return Report(rows=rows)


@router.get("/spend-by-vendor", response_model=Report[VendorSpendRow])
def spend_by_vendor(
    company_id: str | None = Query(default=None),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    currency_mode: CurrencyMode = Query(default="base"),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Report:
    company_ids = resolve_company_ids(scope, company_id)
    rows = reporting.spend_by_vendor(
        session, company_ids, from_date=from_date, to_date=to_date,
        currency_mode=currency_mode,
    )
    return Report(rows=rows)
