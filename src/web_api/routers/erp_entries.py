"""ERP entry (raw GL posting) read endpoints — flat list, voucher groups, detail.

All three read the same joined shape: an entry plus its account and, through the
source invoice, its supplier. `_entry_select`/`_entry_read` are the only path
that builds an `ErpEntryRead`, so a posting looks identical wherever it is
fetched, and `_entry_conditions` is the only place filters are expressed, so the
flat list and the grouped list can never drift apart.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, func, literal, nulls_last
from sqlmodel import Session, select

from web_api.db.models import AuditLog, ErpAccount, ErpEntry, File, Invoice, InvoiceLine, Vendor
from ..deps import TenantScope, get_session, resolve_company_ids, tenant_scope
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
from .invoices import _invoice_read

router = APIRouter(prefix="/api/v1", tags=["erp-entries"])

_ZERO = Decimal("0")

# The grouping key. A voucher id groups postings together; an entry without one
# falls back to its own id so it forms a group of one, rather than every
# voucherless posting in the tenant collapsing into a single bucket. The
# prefixes keep the two namespaces from ever colliding.
_GROUP_KEY = func.coalesce(
    literal("v:", String) + ErpEntry.voucher_id,
    literal("e:", String) + ErpEntry.id,
)

# Entry types this product does not read. A payment settles an invoice already
# accounted for — the money moves, nothing is spent — so it is noise in a spend
# tool, and its postings land on the payable and bank accounts a customer has no
# reason to enable for sync in the first place. Excluded from every entry
# listing rather than filtered per request, because there is no view in which we
# want them back.
#
# Deliberately narrow: `credit_note` (a refund) and `journal_entry` (accruals,
# corrections) stay, since both move real spend.
_EXCLUDED_ENTRY_TYPES = ("payment",)


def _entry_select():
    """Base select yielding `(entry, account_code, account_name, vendor_id,
    vendor_name, account_type, level_1, level_2, level_3)`.

    The account join is inner — `erp_account_id` is a non-null FK. The vendor is
    reached through the source invoice and both hops are optional, and the
    source line is optional too, so those are outer joins.

    Index 5 (`account_type`) is read positionally by `_net_spend`; new columns
    are appended after it for that reason.
    """
    return (
        select(
            ErpEntry,
            ErpAccount.erp_account_code,
            ErpAccount.erp_account_name,
            Vendor.id,
            Vendor.name,
            ErpAccount.erp_account_type,
            # The line's category. Read off the line rather than the entry: a
            # posting is never categorized, its line is.
            InvoiceLine.level_1,
            InvoiceLine.level_2,
            InvoiceLine.level_3,
        )
        .join(ErpAccount, ErpAccount.id == ErpEntry.erp_account_id)
        .outerjoin(Invoice, Invoice.id == ErpEntry.source_invoice_id)
        .outerjoin(Vendor, Vendor.id == Invoice.vendor_id)
        # Outer, and many-entries-to-one-line: most postings (VAT, the payable,
        # journal entries) have no line at all, and the ones that do may share it.
        .outerjoin(InvoiceLine, InvoiceLine.id == ErpEntry.source_invoice_line_id)
    )


# The response fields an ErpEntry can supply itself; the rest come from the join.
_OWN_FIELDS = tuple(
    name
    for name in ErpEntryRead.model_fields
    if name not in {
        "erp_account_code", "erp_account_name", "erp_account_type",
        "vendor_id", "vendor_name",
        "spend_category_level_1", "spend_category_level_2", "spend_category_level_3",
    }
)


def _entry_read(row) -> ErpEntryRead:
    """Build the response model from a `_entry_select()` row."""
    (entry, account_code, account_name, vendor_id, vendor_name, account_type,
     level_1, level_2, level_3) = row
    return ErpEntryRead(
        **{name: getattr(entry, name) for name in _OWN_FIELDS},
        erp_account_code=account_code,
        erp_account_name=account_name,
        erp_account_type=account_type,
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        spend_category_level_1=level_1,
        spend_category_level_2=level_2,
        spend_category_level_3=level_3,
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
) -> list:
    """The WHERE clause shared by every entry listing. Filters compose (AND).

    The excluded-type rule lives here rather than in each endpoint, so the flat
    list and the voucher groups cannot disagree about what exists. An explicit
    `entry_type=payment` therefore returns an empty page rather than overriding
    it — the exclusion is a product rule, not a default.
    """
    conditions = [
        ErpEntry.company_id.in_(company_ids),
        ErpEntry.entry_type.notin_(_EXCLUDED_ENTRY_TYPES),
    ]
    if entry_type is not None:
        conditions.append(ErpEntry.entry_type == entry_type)
    if voucher_id is not None:
        conditions.append(ErpEntry.voucher_id == voucher_id)
    if source_invoice_id is not None:
        conditions.append(ErpEntry.source_invoice_id == source_invoice_id)
    if status_filter is not None:
        conditions.append(ErpEntry.status == status_filter)
    # A null accounting_date compares NULL against a bound, so undated entries
    # drop out of any bounded range — which is what "in this period" means.
    if date_from is not None:
        conditions.append(ErpEntry.accounting_date >= date_from)
    if date_to is not None:
        conditions.append(ErpEntry.accounting_date <= date_to)
    if vendor_id is not None:
        # Entries carry no vendor; the supplier is a property of the invoice the
        # posting came from. An unlinked posting therefore has no known supplier
        # and matches no vendor filter.
        conditions.append(
            ErpEntry.source_invoice_id.in_(
                select(Invoice.id).where(Invoice.vendor_id == vendor_id)
            )
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
    rows = session.exec(
        _entry_select()
        .where(*conditions)
        # Newest first, then a voucher's postings together. Grouping by voucher
        # within a date is what lets this flat list read as a ledger instead of
        # one voucher's rows scattered among every other posting that day. The
        # trailing id makes the order total, so a page boundary can neither
        # repeat nor skip a row. `nulls_last` on both keys because a missing
        # date is not a recent one, and because SQLite and PostgreSQL disagree
        # on where NULLs fall by default.
        .order_by(
            nulls_last(ErpEntry.accounting_date.desc()),
            nulls_last(ErpEntry.voucher_id),
            ErpEntry.id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        items=[_entry_read(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


# Declared before `/erp-entries/{entry_id}`: FastAPI matches in declaration
# order, so the parameterized route would otherwise swallow "vouchers" and 404.
@router.get("/erp-entries/vouchers", response_model=Page[VoucherGroupRead])
def list_voucher_groups(
    company_id: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    source_invoice_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    vendor_id: str | None = Query(default=None),
    currency_mode: CurrencyMode = Query(default="base"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Page[VoucherGroupRead]:
    """Voucher groups, with totals in the company's base currency by default.

    `currency_mode=original` sums the as-posted amounts instead, reproducing the
    behaviour from before base currency existed. Either way, each entry inside a
    group carries both figures, so a client can always explain the total.
    """
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
    )

    # Query 1 — the page of groups. Only the ordering aggregate is selected;
    # totals are derived from the entries themselves in query 2, so what the
    # group claims and what it lists can never disagree.
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
        # NULLS LAST explicitly: Postgres sorts NULLs first on DESC, SQLite last.
        # Without this, undated groups move depending on the backend.
        .order_by(nulls_last(func.max(ErpEntry.accounting_date).desc()), _GROUP_KEY)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    if not keys:
        return Page(items=[], page=page, page_size=page_size, total=total)

    # Query 2 — every entry belonging to the page's groups, in one round-trip.
    # Filtering on the key alone can over-fetch when two companies share a
    # voucher id; bucketing on the (company, key) pair separates them again.
    order = [(company, key) for company, key, _ in keys]
    last_dates = {(company, key): last for company, key, last in keys}
    rows = session.exec(
        _entry_select()
        .where(*conditions, _GROUP_KEY.in_([key for _, key in order]))
        .order_by(ErpEntry.accounting_date, ErpEntry.id)
    ).all()

    buckets: dict[tuple[str, str], list] = {pair: [] for pair in order}
    for row in rows:
        entry = row[0]
        key = f"v:{entry.voucher_id}" if entry.voucher_id is not None else f"e:{entry.id}"
        bucket = buckets.get((entry.company_id, key))
        if bucket is not None:
            bucket.append(row)

    items = [
        _voucher_group(company, key, last_dates[(company, key)],
                       buckets[(company, key)], currency_mode)
        for company, key in order
    ]
    return Page(items=items, page=page, page_size=page_size, total=total)


def _shared(values: list) -> object | None:
    """The one value every entry agrees on, or None if they disagree.

    Nothing in the schema forces a voucher's postings to share a currency or a
    supplier. Reporting the first row's value as the group's would quietly
    invent agreement, so disagreement is reported as "unknown" instead.
    """
    distinct = {v for v in values}
    if len(distinct) == 1:
        return next(iter(distinct))
    return None


# The account type that means "this is money spent". Everything else in a
# voucher is the counterparty (payables, bank) or reclaimable VAT.
_EXPENSE = "expense"

# Which columns a group's totals are summed from, per currency mode. Keeping the
# two side by side is what lets one set of grouping logic serve both without
# either mode quietly acquiring the other's behaviour.
_AMOUNT_FIELDS = {
    "original": ("debit_amount", "credit_amount", "currency"),
    "base": ("base_debit_amount", "base_credit_amount", "base_currency"),
}


def _net_spend(rows: list, debit_field: str, credit_field: str) -> Decimal | None:
    """The group's signed net spend, or None when it spent nothing.

    Deliberately not `debit_total - credit_total`: a voucher balances by
    construction, so that difference is always zero. Spend is the movement on
    the *expense* accounts only — which also makes a credit note come out
    negative on its own, since a refund credits the account it originally
    debited.

    `erp_account_type` is optional on the connector DTO. When no account in the
    group declares one, the caller falls back to the voucher's magnitude rather
    than reporting an empty column for every row.
    """
    expense_rows = [r for r in rows if r[5] == _EXPENSE]
    if not expense_rows:
        return None
    return sum(
        (
            (getattr(r[0], debit_field) or _ZERO) - (getattr(r[0], credit_field) or _ZERO)
            for r in expense_rows
        ),
        _ZERO,
    )


def _voucher_group(
    company_id: str, key: str, last_date, rows: list, mode: str = "base"
) -> VoucherGroupRead:
    entries = [r[0] for r in rows]
    voucher_id = entries[0].voucher_id if entries else None
    debit_field, credit_field, currency_field = _AMOUNT_FIELDS[mode]

    # In base mode, only converted postings can be summed. An unconverted one is
    # counted and left out — folding its posted amount in would add DKK to EUR,
    # and dropping it silently would understate the voucher.
    if mode == "base":
        summable = [r for r in rows if r[0].base_currency is not None]
        unconverted_count = len(rows) - len(summable)
    else:
        summable = rows
        unconverted_count = 0

    if summable:
        debit_total = sum((getattr(r[0], debit_field) or _ZERO for r in summable), _ZERO)
        credit_total = sum((getattr(r[0], credit_field) or _ZERO for r in summable), _ZERO)
        amount = _net_spend(summable, debit_field, credit_field)
        if amount is None and not any(r[5] for r in summable):
            # No account in this group declares a type at all, so "no expense
            # account" is ignorance rather than a fact. Degrade to the voucher's
            # magnitude instead of showing nothing.
            amount = debit_total
    else:
        # Nothing convertible in the whole group: say so, rather than reporting
        # 0.00 in a currency none of these postings are in.
        debit_total = credit_total = amount = None

    return VoucherGroupRead(
        voucher_id=voucher_id,
        company_id=company_id,
        accounting_date=last_date,
        entry_types=sorted({e.entry_type for e in entries}),
        entry_count=len(entries),
        amount=amount,
        debit_total=debit_total,
        credit_total=credit_total,
        currency=_shared([getattr(r[0], currency_field) for r in summable]),
        vendor_id=_shared([r[3] for r in rows]),
        vendor_name=_shared([r[4] for r in rows]),
        unconverted_count=unconverted_count,
        entries=[_entry_read(r) for r in rows],
    )


def _voucher_detail(session: Session, scope: TenantScope, entries: list) -> VoucherDetailRead:
    """Assemble a voucher payload from its postings.

    `_EXCLUDED_ENTRY_TYPES` deliberately does not apply: this is a lookup of a
    voucher the caller named, like `GET /erp-entries/{id}`, not a listing to
    sweep. Dropping a payment here would leave the voucher's totals unexplainable.
    """
    if not entries:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voucher not found")

    reads = [_entry_read(row) for row in entries]
    first = entries[0][0]

    invoice_id = next((r.source_invoice_id for r in reads if r.source_invoice_id), None)
    invoice_payload = None
    document = None
    if invoice_id is not None:
        invoice = session.get(Invoice, invoice_id)
        if invoice is not None and invoice.company_id in scope.company_ids:
            lines = session.exec(
                select(InvoiceLine)
                .where(InvoiceLine.invoice_id == invoice.id)
                .order_by(InvoiceLine.id)
            ).all()
            file_row = (
                session.get(File, invoice.file_id) if invoice.file_id is not None else None
            )
            detail = _invoice_read(invoice, file_row).model_dump()
            detail["lines"] = [InvoiceLineRead.model_validate(ln) for ln in lines]
            invoice_payload = InvoiceDetailRead.model_validate(detail)
            if file_row is not None:
                document = DocumentRead(file_id=file_row.id, filename=file_row.filename)

    currencies = {r.currency for r in reads}
    return VoucherDetailRead(
        voucher_id=first.voucher_id,
        company_id=first.company_id,
        accounting_date=max((r.accounting_date for r in reads if r.accounting_date), default=None),
        # Claimed only when every posting agrees, matching VoucherGroupRead.
        currency=currencies.pop() if len(currencies) == 1 else None,
        entry_count=len(reads),
        entries=reads,
        invoice=invoice_payload,
        document=document,
    )


# Declared before both `/erp-entries/vouchers/{voucher_id}` and
# `/erp-entries/{entry_id}`: FastAPI matches in declaration order, so a
# parameterized route declared first would swallow "by-entry" as a voucher id.
@router.get("/erp-entries/vouchers/by-entry/{entry_id}", response_model=VoucherDetailRead)
def get_voucher_by_entry(
    entry_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> VoucherDetailRead:
    """The voucher a posting belongs to, addressed by the posting.

    A group whose `voucher_id` is null is a group of one and has no shareable
    key of its own; this is how such a group is deep-linked.
    """
    rows = session.exec(
        _entry_select().where(
            ErpEntry.id == entry_id, ErpEntry.company_id.in_(scope.company_ids)
        )
    ).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    voucher_id = rows[0][0].voucher_id
    if voucher_id is not None:
        return get_voucher_detail(voucher_id, scope, session)
    return _voucher_detail(session, scope, list(rows))


# Declared before `/erp-entries/{entry_id}` for the same reason as `vouchers`
# above: a bare `{voucher_id}` path parameter would otherwise swallow it too.
@router.get("/erp-entries/vouchers/{voucher_id}", response_model=VoucherDetailRead)
def get_voucher_detail(
    voucher_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> VoucherDetailRead:
    """One voucher's postings, its invoice with lines, and its document."""
    rows = session.exec(
        _entry_select()
        .where(
            ErpEntry.voucher_id == voucher_id, ErpEntry.company_id.in_(scope.company_ids)
        )
        .order_by(ErpEntry.id)
    ).all()
    return _voucher_detail(session, scope, list(rows))


# Declared before `/erp-entries/vouchers/{voucher_id}/audit` and before
# `/erp-entries/{entry_id}`, for the same reason as `by-entry` above.
@router.get("/erp-entries/vouchers/by-entry/{entry_id}/audit",
            response_model=list[VoucherAuditRead])
def list_voucher_audit_by_entry(
    entry_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[VoucherAuditRead]:
    detail = get_voucher_by_entry(entry_id, scope, session)
    return _voucher_audit(session, detail)


# Declared before `/erp-entries/{entry_id}` for the same reason as `vouchers`
# above: a bare `{voucher_id}` path parameter would otherwise swallow it too.
@router.get("/erp-entries/vouchers/{voucher_id}/audit",
            response_model=list[VoucherAuditRead])
def list_voucher_audit(
    voucher_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[VoucherAuditRead]:
    """Every change to this voucher's invoice and lines, newest first.

    Newest-first because this is a feed — what happened lately. The per-line
    `GET /invoice-lines/{id}/audit` stays oldest-first: a history reads forward.
    """
    detail = get_voucher_detail(voucher_id, scope, session)
    return _voucher_audit(session, detail)


def _voucher_audit(session: Session, detail: VoucherDetailRead) -> list[VoucherAuditRead]:
    """Merge the voucher's invoice- and line-level audit rows into one feed.

    Tenant scope is inherited from the caller: both routes above resolve
    `detail` through the Task 5 resolvers, which already 404 outside the
    caller's scope before any audit row is looked up.
    """
    if detail.invoice is None:
        return []
    labels = {detail.invoice.id: "Invoice"}
    for index, line in enumerate(detail.invoice.lines, start=1):
        labels[line.id] = line.description or f"Line {index}"

    rows = session.exec(
        select(AuditLog)
        .where(AuditLog.entity_id.in_(list(labels)))
        .where(AuditLog.entity_type.in_(["invoice", "invoice_line"]))
        # Newest first, by true insertion order. Not `created_at`: on
        # PostgreSQL that column is constant for the whole transaction, so
        # rows written together (e.g. two lines verified in one request)
        # always tie on it — `seq` is monotonic per row, so no tiebreak
        # column is needed on top of it.
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
    # Deliberately not gated by `_EXCLUDED_ENTRY_TYPES`. That rule governs what
    # we *list*; a lookup by id is reached from a link, and 404-ing a row that
    # exists and is in the caller's tenant would trade a working deep link for
    # nothing — no listing offers the id in the first place.
    row = session.exec(
        _entry_select().where(
            ErpEntry.id == entry_id,
            ErpEntry.company_id.in_(scope.company_ids),
        )
    ).first()
    # 404 rather than 403 for an out-of-scope entry, so existence is not leaked.
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return _entry_read(row)
