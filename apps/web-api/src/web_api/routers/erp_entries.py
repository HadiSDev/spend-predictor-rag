"""ERP entry (raw GL posting) read endpoints — flat list, voucher groups, detail."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, func, literal, nulls_last, or_
from sqlmodel import Session, select

from web_api.db.models import AuditLog, ErpAccount, ErpEntry, File, Invoice, InvoiceLine, Vendor
from web_api.db.models.enums import EXPENSE_ACCOUNT_TYPE
from .. import config
from ..auth.deps import TenantScope, get_session, resolve_company_ids, tenant_scope
from ..schemas import (
    AuditLogRead,
    CurrencyMode,
    DocumentRead,
    ErpEntryRead,
    InvoiceDetailRead,
    InvoiceLineRead,
    Page,
    VoucherAuditRead,
    VoucherDetailRead,
    VoucherGroupRead,
)
from ..reconcile import reconcile_lines
from .entry_rows import EntryRow, InvoiceHeaderState
from .invoices import _invoice_read

router = APIRouter(prefix="/api/v1", tags=["erp-entries"])

_ZERO = Decimal("0")

_GROUP_KEY = func.coalesce(
    literal("v:", String) + ErpEntry.voucher_id,
    literal("e:", String) + ErpEntry.id,
)

_EXCLUDED_ENTRY_TYPES = ("payment",)


def _sync_enabled_condition():
    """A posting is visible only if its account is still selected for sync."""
    return ErpEntry.erp_account_id.in_(
        select(ErpAccount.id).where(ErpAccount.sync_enabled == True)  # noqa: E712
    )


def _entry_select():
    """Base select yielding each entry with its account, vendor and category columns."""
    return (
        select(
            ErpEntry,
            ErpAccount.erp_account_code,
            ErpAccount.erp_account_name,
            Vendor.id,
            Vendor.name,
            ErpAccount.erp_account_type,
            InvoiceLine.level_1,
            InvoiceLine.level_2,
            InvoiceLine.level_3,
        )
        .join(ErpAccount, ErpAccount.id == ErpEntry.erp_account_id)
        .outerjoin(Invoice, Invoice.id == ErpEntry.source_invoice_id)
        .outerjoin(Vendor, Vendor.id == Invoice.vendor_id)
        .outerjoin(InvoiceLine, InvoiceLine.id == ErpEntry.source_invoice_line_id)
    )


_OWN_FIELDS = tuple(
    name
    for name in ErpEntryRead.model_fields
    if name not in {
        "erp_account_code", "erp_account_name", "erp_account_type",
        "vendor_id", "vendor_name",
        "spend_category_level_1", "spend_category_level_2", "spend_category_level_3",
    }
)


def _entry_rows(session: Session, statement) -> list[EntryRow]:
    """Run a `_entry_select()` statement and name its columns."""
    return [EntryRow(*row) for row in session.exec(statement).all()]


def _entry_read(row: EntryRow) -> ErpEntryRead:
    """Build the response model from an entry row."""
    return ErpEntryRead(
        **{name: getattr(row.entry, name) for name in _OWN_FIELDS},
        erp_account_code=row.account_code,
        erp_account_name=row.account_name,
        erp_account_type=row.account_type,
        vendor_id=row.vendor_id,
        vendor_name=row.vendor_name,
        spend_category_level_1=row.level_1,
        spend_category_level_2=row.level_2,
        spend_category_level_3=row.level_3,
    )


def _entry_conditions(
    company_ids: list[str],
    *,
    entry_type: str | None = None,
    voucher_id: str | None = None,
    source_invoice_id: str | None = None,
    status_filter: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    vendor_id: str | None = None,
    needs_review: bool | None = None,
) -> list:
    """The WHERE clause shared by every entry listing."""
    conditions = [
        ErpEntry.company_id.in_(company_ids),
        ErpEntry.entry_type.notin_(_EXCLUDED_ENTRY_TYPES),
        ErpEntry.erp_account_id.in_(
            select(ErpAccount.id).where(ErpAccount.sync_enabled == True)  # noqa: E712
        ),
    ]
    if entry_type is not None:
        conditions.append(ErpEntry.entry_type == entry_type)
    if voucher_id is not None:
        conditions.append(ErpEntry.voucher_id == voucher_id)
    if source_invoice_id is not None:
        conditions.append(ErpEntry.source_invoice_id == source_invoice_id)
    if status_filter is not None:
        conditions.append(ErpEntry.status == status_filter)
    if date_from is not None:
        conditions.append(ErpEntry.accounting_date >= date_from)
    if date_to is not None:
        conditions.append(ErpEntry.accounting_date <= date_to)
    if vendor_id is not None:
        conditions.append(
            ErpEntry.source_invoice_id.in_(
                select(Invoice.id).where(Invoice.vendor_id == vendor_id)
            )
        )
    if needs_review is not None:
        doubtful_invoices = select(InvoiceLine.invoice_id).where(
            InvoiceLine.status == "ai_categorized",
            or_(
                InvoiceLine.confidence.is_(None),
                InvoiceLine.confidence < config.CATEGORIZATION_REVIEW_THRESHOLD,
            ),
        )
        holds_one = ErpEntry.source_invoice_id.in_(doubtful_invoices)
        conditions.append(
            holds_one
            if needs_review
            else or_(~holds_one, ErpEntry.source_invoice_id.is_(None))
        )
    return conditions


@router.get("/erp-entries", response_model=Page[ErpEntryRead])
def list_erp_entries(
    company_id: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    voucher_id: str | None = Query(default=None),
    source_invoice_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    vendor_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Page[ErpEntryRead]:
    company_ids = resolve_company_ids(scope, company_id)
    if not company_ids:
        return Page(items=[], page=page, page_size=page_size, total=0)

    conditions = _entry_conditions(
        company_ids,
        entry_type=entry_type,
        voucher_id=voucher_id,
        source_invoice_id=source_invoice_id,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        vendor_id=vendor_id,
    )

    total = session.exec(
        select(func.count()).select_from(ErpEntry).where(*conditions)
    ).one()
    rows = _entry_rows(
        session,
        _entry_select()
        .where(*conditions)
        .order_by(
            nulls_last(ErpEntry.accounting_date.desc()),
            nulls_last(ErpEntry.voucher_id),
            ErpEntry.id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(
        items=[_entry_read(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/erp-entries/vouchers", response_model=Page[VoucherGroupRead])
def list_voucher_groups(
    company_id: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    source_invoice_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    vendor_id: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    currency_mode: CurrencyMode = Query(default="base"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Page[VoucherGroupRead]:
    """Voucher groups, with totals in the company's base currency by default."""
    company_ids = resolve_company_ids(scope, company_id)
    if not company_ids:
        return Page(items=[], page=page, page_size=page_size, total=0)

    conditions = _entry_conditions(
        company_ids,
        entry_type=entry_type,
        source_invoice_id=source_invoice_id,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        vendor_id=vendor_id,
        needs_review=needs_review,
    )

    grouped = (
        select(
            ErpEntry.company_id,
            _GROUP_KEY.label("group_key"),
            func.max(ErpEntry.accounting_date).label("last_date"),
        )
        .where(*conditions)
        .group_by(ErpEntry.company_id, _GROUP_KEY)
    )
    total = session.exec(
        select(func.count()).select_from(grouped.subquery())
    ).one()
    keys = session.exec(
        grouped
        .order_by(nulls_last(func.max(ErpEntry.accounting_date).desc()), _GROUP_KEY)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    if not keys:
        return Page(items=[], page=page, page_size=page_size, total=total)

    order = [(company, key) for company, key, _ in keys]
    last_dates = {(company, key): last for company, key, last in keys}
    rows = _entry_rows(
        session,
        _entry_select()
        .where(*conditions, _GROUP_KEY.in_([key for _, key in order]))
        .order_by(ErpEntry.accounting_date, ErpEntry.id)
    )

    buckets: dict[tuple[str, str], list[EntryRow]] = {pair: [] for pair in order}
    for row in rows:
        entry = row.entry
        key = f"v:{entry.voucher_id}" if entry.voucher_id is not None else f"e:{entry.id}"
        bucket = buckets.get((entry.company_id, key))
        if bucket is not None:
            bucket.append(row)

    group_invoices = {
        pair: _group_invoice_id(buckets[pair]) for pair in order
    }
    invoice_ids = {inv for inv in group_invoices.values() if inv is not None}
    lines_by_invoice = _invoice_lines_for(session, invoice_ids)
    header_by_invoice = _invoice_header_state(session, invoice_ids)

    items = []
    for company, key in order:
        invoice_id = group_invoices[(company, key)]
        items.append(
            _voucher_group(
                company, key, last_dates[(company, key)],
                buckets[(company, key)], currency_mode,
                lines=lines_by_invoice.get(invoice_id) if invoice_id else None,
                header=header_by_invoice.get(invoice_id) if invoice_id else None,
            )
        )
    return Page(items=items, page=page, page_size=page_size, total=total)


def _shared(values: list) -> object | None:
    """The one value every entry agrees on, or None if they disagree."""
    distinct = {v for v in values}
    if len(distinct) == 1:
        return next(iter(distinct))
    return None


_EXPENSE = EXPENSE_ACCOUNT_TYPE

_AMOUNT_FIELDS = {
    "original": ("debit_amount", "credit_amount", "currency"),
    "base": ("base_debit_amount", "base_credit_amount", "base_currency"),
}


def _net_spend(rows: list[EntryRow], debit_field: str, credit_field: str) -> Decimal | None:
    """The group's signed net spend, or None when it spent nothing."""
    expense_rows = [r for r in rows if r.account_type == _EXPENSE]
    if not expense_rows:
        return None
    return sum(
        (
            (getattr(r.entry, debit_field) or _ZERO) - (getattr(r.entry, credit_field) or _ZERO)
            for r in expense_rows
        ),
        _ZERO,
    )


def _voucher_amount(
    rows: list[EntryRow], mode: str
) -> tuple[Decimal | None, Decimal | None, Decimal | None, str | None, int]:
    """Net spend, debit/credit totals, currency and unconverted count for one voucher."""
    debit_field, credit_field, currency_field = _AMOUNT_FIELDS[mode]

    if mode == "base":
        summable = [r for r in rows if r.entry.base_currency is not None]
        unconverted_count = len(rows) - len(summable)
    else:
        summable = rows
        unconverted_count = 0

    if not summable:
        return None, None, None, None, unconverted_count

    debit_total = sum((getattr(r.entry, debit_field) or _ZERO for r in summable), _ZERO)
    credit_total = sum((getattr(r.entry, credit_field) or _ZERO for r in summable), _ZERO)
    amount = _net_spend(summable, debit_field, credit_field)
    if amount is None and not any(r.account_type for r in summable):
        amount = debit_total
    currency = _shared([getattr(r.entry, currency_field) for r in summable])
    return amount, debit_total, credit_total, currency, unconverted_count


def _invoice_lines_for(session: Session, invoice_ids: set[str]) -> dict[str, list[InvoiceLineRead]]:
    """Every listed voucher's invoice lines, in one round-trip."""
    if not invoice_ids:
        return {}
    rows = session.exec(
        select(InvoiceLine, Invoice.currency)
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .where(InvoiceLine.invoice_id.in_(invoice_ids))  # type: ignore[union-attr]
        .order_by(InvoiceLine.invoice_id, InvoiceLine.sequence, InvoiceLine.id)
    ).all()
    by_invoice: dict[str, list[InvoiceLineRead]] = {}
    for line, currency in rows:
        by_invoice.setdefault(line.invoice_id, []).append(_line_read(line, currency))
    return by_invoice


def _line_read(line: InvoiceLine, currency: str | None) -> InvoiceLineRead:
    """The one place a line payload is built, so every reader agrees on it."""
    return InvoiceLineRead.model_validate(
        {**InvoiceLineRead.model_validate(line).model_dump(), "currency": currency}
    )


def _invoice_header_state(
    session: Session, invoice_ids: set[str]
) -> dict[str, InvoiceHeaderState]:
    """`{invoice_id: InvoiceHeaderState}`, in one round-trip."""
    if not invoice_ids:
        return {}
    rows = session.exec(
        select(
            Invoice.id,
            Invoice.doc_status,
            Invoice.doc_error,
            Invoice.invoice_number,
            Invoice.document_invoice_number,
        ).where(Invoice.id.in_(invoice_ids))  # type: ignore[union-attr]
    ).all()
    return {
        invoice_id: InvoiceHeaderState(str(doc_status), doc_error, number, document_number)
        for invoice_id, doc_status, doc_error, number, document_number in rows
    }


def _group_invoice_id(rows: list[EntryRow]) -> str | None:
    """The source invoice the group's postings agree on, if any."""
    return _shared([r.entry.source_invoice_id for r in rows if r.entry.source_invoice_id])


def _voucher_group(
    company_id: str,
    key: str,
    last_date,
    rows: list[EntryRow],
    mode: str = "base",
    lines: list[InvoiceLineRead] | None = None,
    header: InvoiceHeaderState | None = None,
) -> VoucherGroupRead:
    entries = [r.entry for r in rows]
    voucher_id = entries[0].voucher_id if entries else None
    amount, debit_total, credit_total, currency, unconverted_count = _voucher_amount(rows, mode)

    return VoucherGroupRead(
        voucher_id=voucher_id,
        company_id=company_id,
        accounting_date=last_date,
        entry_types=sorted({e.entry_type for e in entries}),
        entry_count=len(entries),
        amount=amount,
        debit_total=debit_total,
        credit_total=credit_total,
        currency=currency,
        vendor_id=_shared([r.vendor_id for r in rows]),
        vendor_name=_shared([r.vendor_name for r in rows]),
        unconverted_count=unconverted_count,
        entries=[_entry_read(r) for r in rows],
        lines=lines or [],
        doc_status=header.doc_status if header is not None else None,
        doc_error=header.doc_error if header is not None else None,
        invoice_number=header.invoice_number if header is not None else None,
        document_invoice_number=header.document_invoice_number if header is not None else None,
    )


def _voucher_detail(
    session: Session, scope: TenantScope, entries: list[EntryRow], mode: str = "base"
) -> VoucherDetailRead:
    """Assemble a voucher payload from its postings."""
    if not entries:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voucher not found")

    reads = [_entry_read(row) for row in entries]
    first = entries[0].entry

    invoice_id = next((r.source_invoice_id for r in reads if r.source_invoice_id), None)
    invoice_payload = None
    document = None
    if invoice_id is not None:
        invoice = session.get(Invoice, invoice_id)
        if invoice is not None and invoice.company_id in scope.company_ids:
            lines = session.exec(
                select(InvoiceLine)
                .where(InvoiceLine.invoice_id == invoice.id)
                .order_by(InvoiceLine.sequence, InvoiceLine.id)
            ).all()
            file_row = (
                session.get(File, invoice.file_id) if invoice.file_id is not None else None
            )
            detail = _invoice_read(invoice, file_row).model_dump()
            detail["lines"] = [_line_read(ln, invoice.currency) for ln in lines]
            verdict = reconcile_lines(lines, invoice)
            detail["lines_reconciled"] = verdict.ok
            detail["reconciliation_delta"] = verdict.delta
            invoice_payload = InvoiceDetailRead.model_validate(detail)
            if file_row is not None:
                document = DocumentRead(file_id=file_row.id, filename=file_row.filename)

    amount, _debit_total, _credit_total, currency, _unconverted_count = _voucher_amount(
        entries, mode
    )
    return VoucherDetailRead(
        voucher_id=first.voucher_id,
        company_id=first.company_id,
        accounting_date=max((r.accounting_date for r in reads if r.accounting_date), default=None),
        currency=currency,
        amount=amount,
        entry_count=len(reads),
        entries=reads,
        invoice=invoice_payload,
        document=document,
    )


@router.get("/erp-entries/vouchers/by-entry/{entry_id}", response_model=VoucherDetailRead)
def get_voucher_by_entry(
    entry_id: str,
    currency_mode: CurrencyMode = Query(default="base"),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> VoucherDetailRead:
    """The voucher a posting belongs to, addressed by the posting."""
    rows = _entry_rows(
        session,
        _entry_select().where(
            ErpEntry.id == entry_id,
            ErpEntry.company_id.in_(scope.company_ids),
            _sync_enabled_condition(),
        )
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    voucher_id = rows[0].entry.voucher_id
    if voucher_id is not None:
        return get_voucher_detail(voucher_id, currency_mode=currency_mode, scope=scope, session=session)
    return _voucher_detail(session, scope, rows, mode=currency_mode)


@router.get("/erp-entries/vouchers/{voucher_id}", response_model=VoucherDetailRead)
def get_voucher_detail(
    voucher_id: str,
    currency_mode: CurrencyMode = Query(default="base"),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> VoucherDetailRead:
    """One voucher's postings, its invoice with lines, and its document."""
    rows = _entry_rows(
        session,
        _entry_select()
        .where(
            ErpEntry.voucher_id == voucher_id,
            ErpEntry.company_id.in_(scope.company_ids),
            _sync_enabled_condition(),
        )
        .order_by(ErpEntry.id)
    )
    return _voucher_detail(session, scope, rows, mode=currency_mode)


@router.get("/erp-entries/vouchers/by-entry/{entry_id}/audit",
            response_model=list[VoucherAuditRead])
def list_voucher_audit_by_entry(
    entry_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[VoucherAuditRead]:
    detail = get_voucher_by_entry(entry_id, currency_mode="base", scope=scope, session=session)
    return _voucher_audit(session, detail)


@router.get("/erp-entries/vouchers/{voucher_id}/audit",
            response_model=list[VoucherAuditRead])
def list_voucher_audit(
    voucher_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[VoucherAuditRead]:
    """Every change to this voucher's invoice and lines, newest first."""
    detail = get_voucher_detail(voucher_id, currency_mode="base", scope=scope, session=session)
    return _voucher_audit(session, detail)


def _voucher_audit(session: Session, detail: VoucherDetailRead) -> list[VoucherAuditRead]:
    """Merge the voucher's invoice- and line-level audit rows into one feed."""
    if detail.invoice is None:
        return []
    labels = {detail.invoice.id: "Invoice"}
    for index, line in enumerate(detail.invoice.lines, start=1):
        labels[line.id] = line.description or f"Line {index}"

    rows = session.exec(
        select(AuditLog)
        .where(AuditLog.entity_id.in_(list(labels)))
        .where(AuditLog.entity_type.in_(["invoice", "invoice_line"]))
        .order_by(AuditLog.seq.desc())
    ).all()
    return [
        VoucherAuditRead(
            **AuditLogRead.model_validate(row).model_dump(),
            entity_label=labels.get(row.entity_id, row.entity_type),
        )
        for row in rows
    ]


@router.get("/erp-entries/{entry_id}", response_model=ErpEntryRead)
def get_erp_entry(
    entry_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> ErpEntryRead:
    rows = _entry_rows(
        session,
        _entry_select().where(
            ErpEntry.id == entry_id,
            ErpEntry.company_id.in_(scope.company_ids),
        ),
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return _entry_read(rows[0])
