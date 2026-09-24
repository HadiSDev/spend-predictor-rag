"""Invoice-line review — the primary raw/uncategorized data-table surface, plus
human verification of the categorization result and its audit history."""
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
from ..deps import (
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
    needs_review: bool | None = Query(default=None),
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
    if needs_review is not None:
        # The same predicate `InvoiceLineRead.needs_review` derives. Since the
        # model must now return a category rather than declining, this is where
        # the doubt goes: a low confidence is the signal that a human should
        # look, and without a filter it is a number on a row nobody sorts by.
        #
        # `verified` is excluded whatever its confidence — a person has already
        # looked, which is the whole question. `uncategorized` and `ai_failed`
        # are excluded because they are separate backlogs with their own filter.
        doubtful = and_(
            InvoiceLine.status == "ai_categorized",
            or_(
                InvoiceLine.confidence.is_(None),
                InvoiceLine.confidence < config.CATEGORIZATION_REVIEW_THRESHOLD,
            ),
        )
        conditions.append(doubtful if needs_review else ~doubtful)

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
    # The fields the caller **sent**, not the ones that moved: naming a category
    # that is already stored is a human asserting it is right, which is exactly
    # the signal that must survive the next automated write. Same rule as the
    # header's verify endpoint, so both review surfaces produce labels the same
    # way.
    mark_verified(line, corrections.keys())
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


#: What a correction may invalidate, and what that costs. `amount` is the value
#: the line's base figures were derived from; once it moves, they describe
#: nothing real.
_LINE_FX_TRIGGER = "amount"


@router.patch("/invoice-lines/{line_id}", response_model=InvoiceLineRead)
def update_invoice_line(
    line_id: str,
    body: InvoiceLineUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> InvoiceLine:
    """Correct what a line says was bought (management only).

    Separate from `verify` above, and deliberately so: a category is chosen from
    the company's tree and validated against it, while these are free values a
    human read off a document. `InvoiceLineUpdate` forbids extra fields, so a
    `spend_category_id` sent here is a `422` rather than a silently ignored
    field that reads to the caller as a category edit that did nothing.

    Applied in place. The audit diff's `old` is the only surviving record of
    what the ERP or the extractor originally stated.
    """
    line = _get_scoped_line(session, scope, line_id)
    fields = LINE_VALUE_AUDIT_FIELDS + LINE_BASE_FX_FIELDS

    corrections = body.model_dump(exclude_unset=True)
    before = {f: getattr(line, f) for f in fields}
    for field, value in corrections.items():
        setattr(line, field, value)

    # The line's conversion was derived from its `amount`. Cleared rather than
    # recomputed inline, for the reason `update_invoice` states at length: this
    # endpoint makes no network call, and converting at a substitute rate is
    # what the currency design rejects. `POST /companies/{id}/recompute-fx`
    # restores it at the row's own historical rate.
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
    # The rollup reads the lines' *statuses*, which a value correction does not
    # touch — but it is recomputed anyway so this endpoint cannot become the one
    # write path that leaves the invoice's status behind.
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
    """Add a line to an invoice (management only).

    The way a reviewer splits a stand-in line into what was actually bought: add
    the real lines, then delete the stand-in. The invoice holds both origins in
    between, which the one-origin rule permits precisely for `human` lines —
    forbidding the intermediate state would make the operation impossible
    without a bulk replace endpoint nobody asked for, and the reconciliation
    warning is what covers it.

    `origin` is not a parameter. A line created here is `human` by
    construction, which is what makes "a sync never displaces it" a fact rather
    than a claim the caller could get wrong.
    """
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.company_id not in scope.company_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    values = body.model_dump(exclude_unset=True)
    sequence = values.pop("sequence", None)
    if sequence is None:
        # After the last line, which is what appending means. `max` over the
        # loaded rows rather than a `func.max` query: the invoice's lines are a
        # handful, and one query beats two.
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
    session.flush()  # assign the id the audit entry names

    # Recorded against the **invoice**: a line's own history starts here, and
    # what a reader of the invoice needs to know is that its line set changed.
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
    """Delete a line (management only), keeping its values in the audit trail.

    Hard, not soft: a soft-delete flag would have to be understood by every
    reader — the reports, the categorizer, the reconciler, the entry payload's
    category resolution — and one that forgot would quietly double-count. The
    audit entry preserves the record instead, carrying the line's values and its
    categorization, which for a verified line is the only surviving trace that a
    human's decision ever existed.

    Its postings survive it. An `ErpEntry` is the ledger's own evidence and is
    never deleted with a line; the reference is nulled, exactly as the document
    stage does when an extraction replaces the lines a posting pointed at.
    """
    line = _get_scoped_line(session, scope, line_id)
    invoice_id = line.invoice_id

    # The whole line, not just its categorization: this row is the only place
    # its description and amount will exist a moment from now.
    snapshot = [
        {"field": f, "old": audit_value(getattr(line, f)), "new": None}
        for f in LINE_VALUE_AUDIT_FIELDS + LINE_AUDIT_FIELDS
        if getattr(line, f) is not None
    ]
    record_audit(
        session, entity_type="invoice_line", entity_id=line.id,
        action="line_deleted", actor=scope.user_id, changes=snapshot,
    )
    # And on the invoice, because the line's own history becomes unreachable
    # through a row that no longer exists — nobody browsing the invoice would
    # think to look up an id they can no longer see.
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
    """Change history for a line, oldest first. Tenant-scoped via the line."""
    _get_scoped_line(session, scope, line_id)
    return session.exec(
        select(AuditLog)
        .where(AuditLog.entity_type == "invoice_line", AuditLog.entity_id == line_id)
        .order_by(AuditLog.created_at, AuditLog.id)
    ).all()
