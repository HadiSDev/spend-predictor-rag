"""Spend trees: the organization's categorization taxonomies."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from web_api.db.models import (
    Company,
    Invoice,
    InvoiceLine,
    SpendCategory,
    SpendCategorySuggestion,
    SpendTree,
    SuggestionState,
    Vendor,
)
from ..auth.deps import TenantScope, get_session, require_management, tenant_scope
from ..schemas import (
    SpendCategoryCreate,
    SpendCategoryRead,
    SpendCategoryUpdate,
    SpendTreeCreate,
    SpendTreeDeleteResult,
    SpendTreeDetailRead,
    SpendTreeImportResult,
    SpendTreeRead,
    SpendTreeUpdate,
    SpendCategorySuggestionRead,
    SuggestionEvidenceRead,
    SuggestionResolveResult,
)
from ..spend_trees import importer, service

router = APIRouter(prefix="/api/v1", tags=["spend-trees"])

_STATUS_BY_CODE = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "conflict": status.HTTP_409_CONFLICT,
    "invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _http(error: service.SpendTreeError) -> HTTPException:
    """Map a service rule violation to its status code."""
    detail: object = error.message
    if isinstance(error, importer.ImportRejected):
        detail = {
            "message": error.message,
            "errors": [{"line": e.line, "message": e.message} for e in error.errors],
        }
    return HTTPException(status_code=_STATUS_BY_CODE[error.code], detail=detail)


def _tree_read(session: Session, tree: SpendTree, *, with_nodes: bool = False):
    node_count = len(
        session.exec(
            select(SpendCategory.id).where(SpendCategory.spend_tree_id == tree.id)
        ).all()
    )
    companies = session.exec(
        select(Company).where(Company.spend_tree_id == tree.id).order_by(Company.name)
    ).all()
    payload = {
        "id": tree.id,
        "name": tree.name,
        "max_depth": tree.max_depth,
        "source": tree.source.value if hasattr(tree.source, "value") else tree.source,
        "template_version": tree.template_version,
        "archived_at": tree.archived_at,
        "created_at": tree.created_at,
        "node_count": node_count,
        "company_ids": [c.id for c in companies],
        "company_names": [c.name for c in companies],
    }
    if not with_nodes:
        return SpendTreeRead(**payload)
    return SpendTreeDetailRead(
        **payload,
        nodes=[SpendCategoryRead.model_validate(n) for n in service.tree_nodes(session, tree.id)],
    )


def _get_tree(session: Session, scope: TenantScope, tree_id: str) -> SpendTree:
    try:
        return service.get_tree(session, tree_id, scope.organization_id)
    except service.SpendTreeError as error:
        raise _http(error) from error


@router.get("/spend-trees", response_model=list[SpendTreeRead])
def list_spend_trees(
    include_archived: bool = Query(default=False),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[SpendTreeRead]:
    stmt = select(SpendTree).where(SpendTree.organization_id == scope.organization_id)
    if not include_archived:
        stmt = stmt.where(SpendTree.archived_at.is_(None))
    trees = session.exec(stmt.order_by(SpendTree.name, SpendTree.id)).all()
    return [_tree_read(session, tree) for tree in trees]


@router.get("/spend-trees/{tree_id}", response_model=SpendTreeDetailRead)
def get_spend_tree(
    tree_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> SpendTreeDetailRead:
    """One tree with all its nodes."""
    return _tree_read(session, _get_tree(session, scope, tree_id), with_nodes=True)


@router.post("/spend-trees/default", response_model=SpendTreeDetailRead)
def ensure_default_spend_tree(
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SpendTreeDetailRead:
    """The organization's copy of the platform template, created if absent."""
    tree = service.ensure_default_tree(session, scope.organization_id)
    session.commit()
    session.refresh(tree)
    return _tree_read(session, tree, with_nodes=True)


@router.post("/spend-trees", response_model=SpendTreeDetailRead,
             status_code=status.HTTP_201_CREATED)
def create_spend_tree(
    body: SpendTreeCreate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SpendTreeDetailRead:
    """Create a tree — empty, or cloned from one of the organization's own."""
    try:
        if body.source_tree_id is not None:
            source = service.get_tree(session, body.source_tree_id, scope.organization_id)
            tree = service.clone_tree(session, source, body.name, max_depth=body.max_depth)
        else:
            tree = service.create_tree(
                session, scope.organization_id, body.name, max_depth=body.max_depth
            )
    except service.SpendTreeError as error:
        raise _http(error) from error

    session.commit()
    session.refresh(tree)
    return _tree_read(session, tree, with_nodes=True)


@router.patch("/spend-trees/{tree_id}", response_model=SpendTreeRead)
def update_spend_tree(
    tree_id: str,
    body: SpendTreeUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SpendTreeRead:
    tree = _get_tree(session, scope, tree_id)
    try:
        service.update_tree(session, tree, name=body.name, max_depth=body.max_depth)
    except service.SpendTreeError as error:
        raise _http(error) from error
    session.commit()
    session.refresh(tree)
    return _tree_read(session, tree)


@router.post("/spend-trees/{tree_id}/archive", response_model=SpendTreeRead)
def archive_spend_tree(
    tree_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SpendTreeRead:
    """Soft-archive."""
    tree = _get_tree(session, scope, tree_id)
    try:
        service.archive_tree(session, tree)
    except service.SpendTreeError as error:
        raise _http(error) from error
    session.commit()
    session.refresh(tree)
    return _tree_read(session, tree)


@router.delete("/spend-trees/{tree_id}", response_model=SpendTreeDeleteResult)
def delete_spend_tree(
    tree_id: str,
    confirm: bool = Query(default=False),
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SpendTreeDeleteResult:
    """Delete a tree and its nodes."""
    tree = _get_tree(session, scope, tree_id)
    try:
        stale = service.delete_tree(session, tree, confirm=confirm)
    except service.SpendTreeError as error:
        raise _http(error) from error
    session.commit()
    return SpendTreeDeleteResult(stale_lines=stale)


@router.post("/spend-trees/{tree_id}/import", response_model=SpendTreeImportResult)
def import_spend_tree(
    tree_id: str,
    content: str = Body(..., embed=True),
    mode: str = Query(default=importer.MERGE, pattern="^(merge|replace)$"),
    confirm: bool = Query(default=False),
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SpendTreeImportResult:
    """Load a CSV of `level_1..level_4` (+ `description`, `code`) into a tree."""
    tree = _get_tree(session, scope, tree_id)
    try:
        plan = importer.plan_import(session, tree, content, mode=mode)
    except service.SpendTreeError as error:
        raise _http(error) from error

    if plan.affected_lines and not confirm:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    f"This import removes categories that {len(plan.affected_lines)} "
                    "invoice line(s) are assigned to. Those lines keep their "
                    "categories on record but will need reviewing."
                ),
                "affected_lines": len(plan.affected_lines),
                "removed_nodes": len(plan.removed),
            },
        )

    result = importer.apply_import(session, tree, plan)
    session.commit()
    return SpendTreeImportResult(**result)


@router.post("/spend-trees/{tree_id}/nodes", response_model=SpendCategoryRead,
             status_code=status.HTTP_201_CREATED)
def create_spend_category(
    tree_id: str,
    body: SpendCategoryCreate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SpendCategory:
    tree = _get_tree(session, scope, tree_id)
    try:
        node = service.add_node(
            session, tree, body.name, parent_id=body.parent_id, code=body.code,
            description=body.description, sort_order=body.sort_order,
        )
    except service.SpendTreeError as error:
        raise _http(error) from error
    session.commit()
    session.refresh(node)
    return node


@router.patch("/spend-tree-nodes/{node_id}", response_model=SpendCategoryRead)
def update_spend_category(
    node_id: str,
    body: SpendCategoryUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SpendCategory:
    try:
        node = service.get_node(session, node_id, scope.organization_id)
        if "parent_id" in body.model_fields_set:
            service.move_node(session, node, body.parent_id)
        service.update_node(
            session, node, name=body.name, code=body.code,
            description=body.description, sort_order=body.sort_order,
        )
    except service.SpendTreeError as error:
        raise _http(error) from error
    session.commit()
    session.refresh(node)
    return node


@router.delete("/spend-tree-nodes/{node_id}", response_model=SpendTreeDeleteResult)
def delete_spend_category(
    node_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SpendTreeDeleteResult:
    """Delete a leaf."""
    try:
        node = service.get_node(session, node_id, scope.organization_id)
        stale = service.delete_node(session, node)
    except service.SpendTreeError as error:
        raise _http(error) from error
    session.commit()
    return SpendTreeDeleteResult(stale_lines=stale)


def _path_of(node: SpendCategory | None) -> str | None:
    if node is None:
        return None
    return " > ".join(
        x for x in (node.level_1, node.level_2, node.level_3, node.level_4) if x
    )


def _suggestion_read(
    session: Session, row: SpendCategorySuggestion, *, with_evidence: bool = True
) -> SpendCategorySuggestionRead:
    parent = session.get(SpendCategory, row.parent_id) if row.parent_id else None
    ids = list(row.evidence_line_ids or [])
    evidence: list[SuggestionEvidenceRead] = []
    if with_evidence and ids:
        lines = session.exec(
            select(InvoiceLine).where(InvoiceLine.id.in_(ids))  # type: ignore[union-attr]
        ).all()
        invoices = {
            inv.id: inv for inv in session.exec(
                select(Invoice).where(
                    Invoice.id.in_({line.invoice_id for line in lines})  # type: ignore[union-attr]
                )
            ).all()
        } if lines else {}
        vendors = {
            v.id: v.name for v in session.exec(
                select(Vendor).where(
                    Vendor.id.in_({
                        inv.vendor_id for inv in invoices.values() if inv.vendor_id
                    })  # type: ignore[union-attr]
                )
            ).all()
        } if invoices else {}
        for line in lines:
            invoice = invoices.get(line.invoice_id)
            evidence.append(SuggestionEvidenceRead(
                id=line.id, item_name=line.item_name, description=line.description,
                amount=line.amount, currency=invoice.currency if invoice else None,
                vendor_name=vendors.get(invoice.vendor_id) if invoice else None,
                invoice_id=line.invoice_id,
                level_1=line.level_1, level_2=line.level_2, level_3=line.level_3,
                confidence=line.confidence,
            ))

    return SpendCategorySuggestionRead(
        id=row.id, spend_tree_id=row.spend_tree_id, company_id=row.company_id,
        parent_id=row.parent_id, parent_path=_path_of(parent),
        name=row.name, description=row.description, rationale=row.rationale,
        state=row.state, created_category_id=row.created_category_id,
        acceptable=row.state == SuggestionState.PENDING and parent is not None,
        evidence=evidence, evidence_count=len(ids),
        created_at=row.created_at,
    )


def _get_suggestion(
    session: Session, scope: TenantScope, suggestion_id: str
) -> SpendCategorySuggestion:
    """One suggestion, scoped through the tree it belongs to."""
    row = session.get(SpendCategorySuggestion, suggestion_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found"
        )
    _get_tree(session, scope, row.spend_tree_id)
    return row


@router.get(
    "/spend-trees/{tree_id}/suggestions",
    response_model=list[SpendCategorySuggestionRead],
)
def list_spend_tree_suggestions(
    tree_id: str,
    state: str | None = Query(default=SuggestionState.PENDING),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[SpendCategorySuggestionRead]:
    """This tree's suggestions, pending by default."""
    tree = _get_tree(session, scope, tree_id)
    stmt = select(SpendCategorySuggestion).where(
        SpendCategorySuggestion.spend_tree_id == tree.id
    )
    if state is not None:
        stmt = stmt.where(SpendCategorySuggestion.state == state)
    rows = session.exec(
        stmt.order_by(SpendCategorySuggestion.created_at, SpendCategorySuggestion.id)
    ).all()
    return [_suggestion_read(session, row) for row in rows]


@router.post(
    "/spend-tree-suggestions/{suggestion_id}/accept",
    response_model=SuggestionResolveResult,
)
def accept_spend_tree_suggestion(
    suggestion_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SuggestionResolveResult:
    """Create the proposed node, through the same service any node goes through."""
    row = _get_suggestion(session, scope, suggestion_id)
    if row.state != SuggestionState.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This suggestion was already {row.state}.",
        )
    tree = _get_tree(session, scope, row.spend_tree_id)
    parent = session.get(SpendCategory, row.parent_id) if row.parent_id else None
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The category this suggestion would be added under no longer "
                "exists. Add the category by hand if you still want it."
            ),
        )
    try:
        node = service.add_node(
            session, tree, row.name, parent_id=parent.id, description=row.description,
        )
    except service.SpendTreeError as error:
        raise _http(error) from error

    row.state = SuggestionState.ACCEPTED
    row.created_category_id = node.id
    row.resolved_by = scope.user_id
    row.resolved_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    return SuggestionResolveResult(
        id=row.id, state=row.state, created_category_id=node.id
    )


@router.post(
    "/spend-tree-suggestions/{suggestion_id}/reopen",
    response_model=SuggestionResolveResult,
)
def reopen_spend_tree_suggestion(
    suggestion_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SuggestionResolveResult:
    """Put a dismissed suggestion back in front of the reviewer."""
    row = _get_suggestion(session, scope, suggestion_id)
    if row.state != SuggestionState.DISMISSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only a dismissed suggestion can be reopened; this one is {row.state}.",
        )
    row.state = SuggestionState.PENDING
    row.resolved_by = None
    row.resolved_at = None
    session.add(row)
    session.commit()
    return SuggestionResolveResult(id=row.id, state=row.state)


@router.post(
    "/spend-tree-suggestions/{suggestion_id}/dismiss",
    response_model=SuggestionResolveResult,
)
def dismiss_spend_tree_suggestion(
    suggestion_id: str,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SuggestionResolveResult:
    """Refuse the proposal, and remember the refusal."""
    row = _get_suggestion(session, scope, suggestion_id)
    if row.state == SuggestionState.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This suggestion was already accepted.",
        )
    row.state = SuggestionState.DISMISSED
    row.resolved_by = scope.user_id
    row.resolved_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    return SuggestionResolveResult(id=row.id, state=row.state)
