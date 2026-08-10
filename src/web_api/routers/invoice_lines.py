"""Invoice-line review — the primary raw/uncategorized data-table surface, plus
human verification of the categorization result and its audit history."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_
from sqlmodel import Session, select

from web_api.db.models import (
    AuditLog,
    Company,
    ErpEntry,
    Invoice,
    InvoiceLine,
    LineStatus,
    SpendCategory,
)
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


def _resolve_node_for_line(
    session: Session, line: InvoiceLine, node_id: str
) -> SpendCategory:
    """The spend category a correction names, or 422.

    Validated against the **company's assigned tree**, not merely against
    existence: a node from another tree would store a pointer the company's own
    taxonomy cannot resolve, which is the stale state — reachable by accident,
    never by a write.
    """
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
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Page[InvoiceLine]:
    """The line-level view of spend, filtered the way the Entries page filters.

    A line carries no date, no supplier and no voucher of its own, so three of
    these resolve through its invoice:

    * `from`/`to` bound the **invoice date** — the same date the line was
      converted at, so a filtered period and the amounts shown for it agree.
    * `vendor_id` matches the invoice's supplier.
    * `voucher_id` matches through the invoice's postings, so a caller holding a
      voucher can ask for the lines behind it.
    """
    company_ids = resolve_company_ids(scope, company_id)
    if not company_ids:
        return Page(items=[], page=page, page_size=page_size, total=0)

    conditions = [InvoiceLine.company_id.in_(company_ids)]
    if status_filter is not None:
        conditions.append(InvoiceLine.status == status_filter)
    if origin is not None:
        conditions.append(InvoiceLine.origin == origin)
    if stale is not None:
        # The same predicate `InvoiceLineRead.category_stale` derives: a line
        # that carries a decision but points at no node. This is the backlog a
        # tree change creates, and without a filter a reviewer would have to
        # page through everything to find it.
        decided = or_(InvoiceLine.level_1.is_not(None), InvoiceLine.level_2.is_not(None))
        unresolved = InvoiceLine.spend_category_id.is_(None)
        conditions.append(and_(decided, unresolved) if stale else ~and_(decided, unresolved))

    # Resolved as subqueries on `invoice_id` rather than as joins: a join would
    # multiply a line by its invoice's postings and a voucher filter would then
    # return the same line several times.
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
    """Verify a line's categorization (management only), optionally correcting it.

    Applies any provided category fields, marks the line ``verified``, records an
    ``AuditLog`` entry attributed to the acting user, and recomputes the invoice
    rollup — all in one transaction.

    **Naming a `spend_category_id` is the correct way to correct a category.**
    The server then takes `level_1..level_4` from that node's path and ignores
    any levels the caller also sent: the node is the authority, and a correction
    made this way always resolves to a real row. Typed levels that match no node
    produce a categorization that resolves to nothing — the silent failure the
    stored pointer exists to prevent — which is why the client sends a node.
    """
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
