"""Invoice-line review: listing, verification, corrections and audit history."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_
from sqlmodel import Session, select

from web_api.db.models import (
    AuditLog,
    Company,
    ErpEntry,
    Invoice,
    InvoiceLine,
    LineOrigin,
    LineStatus,
    SpendCategory,
)
from .. import config
from ..audit import (
    LINE_AUDIT_FIELDS,
    LINE_BASE_FX_FIELDS,
    LINE_VALUE_AUDIT_FIELDS,
    audit_value,
    diff_changes,
    record_audit,
)
from ..auth.deps import (
    TenantScope,
    get_session,
    require_management,
    resolve_company_ids,
    tenant_scope,
)
from ..rollup import recompute_invoice_status
from ..schemas import (
    AuditLogRead,
    InvoiceLineCreate,
    InvoiceLineRead,
    InvoiceLineUpdate,
    InvoiceLineVerify,
    Page,
)
from ..verified import mark_verified

router = APIRouter(prefix="/api/v1", tags=["invoice-lines"])


def _get_scoped_line(session: Session, scope: TenantScope, line_id: str) -> InvoiceLine:
    """Fetch a line the caller may see, or raise 404."""
    line = session.get(InvoiceLine, line_id)
    if line is None or (
        not scope.is_system_admin and line.company_id not in scope.company_ids
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice line not found")
    return line


def _resolve_node_for_line(
    session: Session, line: InvoiceLine, node_id: str
) -> SpendCategory:
    """The spend category a correction names, or 422."""
    company = session.get(Company, line.company_id)
    node = session.get(SpendCategory, node_id)
    if (
        node is None
        or company is None
        or company.spend_tree_id is None
        or node.spend_tree_id != company.spend_tree_id
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That spend category is not in this company's spend tree.",
        )
    return node


@router.get("/invoice-lines", response_model=Page[InvoiceLineRead])
def list_invoice_lines(
    status_filter: str | None = Query(default=None, alias="status"),
    company_id: str | None = Query(default=None),
    vendor_id: str | None = Query(default=None),
    voucher_id: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    stale: bool | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Page[InvoiceLine]:
    """The line-level view of spend, filtered the way the Entries page filters."""
    company_ids = resolve_company_ids(scope, company_id)
    if not company_ids:
        return Page(items=[], page=page, page_size=page_size, total=0)

    conditions = [InvoiceLine.company_id.in_(company_ids)]
    if status_filter is not None:
        conditions.append(InvoiceLine.status == status_filter)
    if origin is not None:
        conditions.append(InvoiceLine.origin == origin)
    if stale is not None:
        decided = or_(InvoiceLine.level_1.is_not(None), InvoiceLine.level_2.is_not(None))
        unresolved = InvoiceLine.spend_category_id.is_(None)
        conditions.append(and_(decided, unresolved) if stale else ~and_(decided, unresolved))
    if needs_review is not None:
        doubtful = and_(
            InvoiceLine.status == "ai_categorized",
            or_(
                InvoiceLine.confidence.is_(None),
                InvoiceLine.confidence < config.CATEGORIZATION_REVIEW_THRESHOLD,
            ),
        )
        conditions.append(doubtful if needs_review else ~doubtful)

    if vendor_id is not None or date_from is not None or date_to is not None:
        invoice_conditions = []
        if vendor_id is not None:
            invoice_conditions.append(Invoice.vendor_id == vendor_id)
        if date_from is not None:
            invoice_conditions.append(Invoice.invoice_date >= date_from)
        if date_to is not None:
            invoice_conditions.append(Invoice.invoice_date <= date_to)
        conditions.append(
            InvoiceLine.invoice_id.in_(select(Invoice.id).where(*invoice_conditions))
        )
    if voucher_id is not None:
        conditions.append(
            InvoiceLine.invoice_id.in_(
                select(ErpEntry.source_invoice_id).where(
                    ErpEntry.voucher_id == voucher_id,
                    ErpEntry.source_invoice_id.is_not(None),
                )
            )
        )

    total = session.exec(
        select(func.count()).select_from(InvoiceLine).where(*conditions)
    ).one()
    rows = session.exec(
        select(InvoiceLine)
        .where(*conditions)
        .order_by(InvoiceLine.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=rows, page=page, page_size=page_size, total=total)


@router.post("/invoice-lines/{line_id}/verify", response_model=InvoiceLineRead)
def verify_invoice_line(
    line_id: str,
    body: InvoiceLineVerify | None = None,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> InvoiceLine:
    """Verify a line's categorization (management only), optionally correcting it."""
    line = _get_scoped_line(session, scope, line_id)

    before = {f: getattr(line, f) for f in LINE_AUDIT_FIELDS}

    corrections = (body.model_dump(exclude_unset=True) if body is not None else {})
    node_id = corrections.get("spend_category_id")
    if node_id is not None:
        node = _resolve_node_for_line(session, line, node_id)
        corrections.update({
            "level_1": node.level_1,
            "level_2": node.level_2,
            "level_3": node.level_3,
            "level_4": node.level_4,
        })

    for field, value in corrections.items():
        setattr(line, field, value)
    line.status = LineStatus.VERIFIED
    mark_verified(line, corrections.keys())
    session.add(line)

    after = {f: getattr(line, f) for f in LINE_AUDIT_FIELDS}
    corrected_fields = set(corrections) & set(LINE_AUDIT_FIELDS)
    action = "edit" if corrected_fields else "verify"
    record_audit(
        session,
        entity_type="invoice_line",
        entity_id=line.id,
        action=action,
        actor=scope.user_id,
        changes=diff_changes(before, after, LINE_AUDIT_FIELDS),
    )

    recompute_invoice_status(session, line.invoice_id)
    session.commit()
    session.refresh(line)
    return line


_LINE_FX_TRIGGER = "amount"


@router.patch("/invoice-lines/{line_id}", response_model=InvoiceLineRead)
def update_invoice_line(
    line_id: str,
    body: InvoiceLineUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> InvoiceLine:
    """Correct what a line says was bought (management only)."""
    line = _get_scoped_line(session, scope, line_id)
    fields = LINE_VALUE_AUDIT_FIELDS + LINE_BASE_FX_FIELDS

    corrections = body.model_dump(exclude_unset=True)
    before = {f: getattr(line, f) for f in fields}
    for field, value in corrections.items():
        setattr(line, field, value)

    if getattr(line, _LINE_FX_TRIGGER) != before[_LINE_FX_TRIGGER]:
        line.base_currency = None
        line.base_amount = None
        line.fx_rate = None
        line.fx_rate_date = None

    mark_verified(line, corrections.keys())
    session.add(line)

    after = {f: getattr(line, f) for f in fields}
    changes = diff_changes(before, after, fields)
    record_audit(
        session,
        entity_type="invoice_line",
        entity_id=line.id,
        action="edit" if changes else "noop",
        actor=scope.user_id,
        changes=changes,
    )
    recompute_invoice_status(session, line.invoice_id)
    session.commit()
    session.refresh(line)
    return line


@router.post(
    "/invoices/{invoice_id}/lines",
    response_model=InvoiceLineRead,
    status_code=status.HTTP_201_CREATED,
)
def create_invoice_line(
    invoice_id: str,
    body: InvoiceLineCreate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> InvoiceLine:
    """Add a line to an invoice (management only)."""
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.company_id not in scope.company_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    values = body.model_dump(exclude_unset=True)
    sequence = values.pop("sequence", None)
    if sequence is None:
        last = session.exec(
            select(func.max(InvoiceLine.sequence)).where(InvoiceLine.invoice_id == invoice_id)
        ).one()
        sequence = 0 if last is None else last + 1

    line = InvoiceLine(
        company_id=invoice.company_id,
        invoice_id=invoice.id,
        origin=LineOrigin.HUMAN,
        status=LineStatus.UNCATEGORIZED,
        sequence=sequence,
        **values,
    )
    session.add(line)
    session.flush()

    record_audit(
        session,
        entity_type="invoice",
        entity_id=invoice.id,
        action="line_added",
        actor=scope.user_id,
        changes=[{"field": "line_id", "old": None, "new": line.id}],
    )
    recompute_invoice_status(session, invoice.id)
    session.commit()
    session.refresh(line)
    return line


@router.delete("/invoice-lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice_line(
    line_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a line (management only), keeping its values in the audit trail."""
    line = _get_scoped_line(session, scope, line_id)
    invoice_id = line.invoice_id

    snapshot = [
        {"field": f, "old": audit_value(getattr(line, f)), "new": None}
        for f in LINE_VALUE_AUDIT_FIELDS + LINE_AUDIT_FIELDS
        if getattr(line, f) is not None
    ]
    record_audit(
        session, entity_type="invoice_line", entity_id=line.id,
        action="line_deleted", actor=scope.user_id, changes=snapshot,
    )
    record_audit(
        session, entity_type="invoice", entity_id=invoice_id,
        action="line_deleted", actor=scope.user_id,
        changes=[{"field": "line_id", "old": line.id, "new": None}],
    )

    for entry in session.exec(
        select(ErpEntry).where(ErpEntry.source_invoice_line_id == line_id)
    ).all():
        entry.source_invoice_line_id = None
        session.add(entry)

    session.delete(line)
    recompute_invoice_status(session, invoice_id)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/invoice-lines/{line_id}/audit", response_model=list[AuditLogRead])
def list_invoice_line_audit(
    line_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[AuditLog]:
    """Change history for a line, oldest first."""
    _get_scoped_line(session, scope, line_id)
    return session.exec(
        select(AuditLog)
        .where(AuditLog.entity_type == "invoice_line", AuditLog.entity_id == line_id)
        .order_by(AuditLog.created_at, AuditLog.id)
    ).all()
