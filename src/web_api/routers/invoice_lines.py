"""Invoice-line review — the primary raw/uncategorized data-table surface, plus
human verification of the categorization result and its audit history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, select

from web_api.db.models import AuditLog, InvoiceLine, LineStatus
from ..audit import LINE_AUDIT_FIELDS, diff_changes, record_audit
from ..deps import (
    TenantScope,
    get_session,
    require_management,
    resolve_company_ids,
    tenant_scope,
)
from ..rollup import recompute_invoice_status
from ..schemas import AuditLogRead, InvoiceLineRead, InvoiceLineVerify, Page

router = APIRouter(prefix="/api/v1", tags=["invoice-lines"])


def _get_scoped_line(session: Session, scope: TenantScope, line_id: str) -> InvoiceLine:
    """Fetch a line the caller may see, or raise 404. Never a window into another
    tenant: a foreign line is indistinguishable from a missing one."""
    line = session.get(InvoiceLine, line_id)
    if line is None or (
        not scope.is_system_admin and line.company_id not in scope.company_ids
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice line not found")
    return line


@router.get("/invoice-lines", response_model=Page[InvoiceLineRead])
def list_invoice_lines(
    status_filter: str | None = Query(default=None, alias="status"),
    company_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Page[InvoiceLine]:
    company_ids = resolve_company_ids(scope, company_id)
    if not company_ids:
        return Page(items=[], page=page, page_size=page_size, total=0)

    conditions = [InvoiceLine.company_id.in_(company_ids)]
    if status_filter is not None:
        conditions.append(InvoiceLine.status == status_filter)

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
    """Verify a line's categorization (management only), optionally correcting it.

    Applies any provided category fields, marks the line ``verified``, records an
    ``AuditLog`` entry attributed to the acting user, and recomputes the invoice
    rollup — all in one transaction.
    """
    line = _get_scoped_line(session, scope, line_id)

    before = {f: getattr(line, f) for f in LINE_AUDIT_FIELDS}

    corrections = (body.model_dump(exclude_unset=True) if body is not None else {})
    for field, value in corrections.items():
        setattr(line, field, value)
    line.status = LineStatus.VERIFIED
    session.add(line)

    after = {f: getattr(line, f) for f in LINE_AUDIT_FIELDS}
    # "edit" when the caller changed category values, otherwise a plain "verify".
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


@router.get("/invoice-lines/{line_id}/audit", response_model=list[AuditLogRead])
def list_invoice_line_audit(
    line_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[AuditLog]:
    """Change history for a line, oldest first. Tenant-scoped via the line."""
    _get_scoped_line(session, scope, line_id)
    return session.exec(
        select(AuditLog)
        .where(AuditLog.entity_type == "invoice_line", AuditLog.entity_id == line_id)
        .order_by(AuditLog.created_at, AuditLog.id)
    ).all()
