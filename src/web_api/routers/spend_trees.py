"""Spend trees: the organization's categorization taxonomies.

Reads are open to any authenticated member — a reviewer picking a category needs
the tree, and gating that behind management would make the selector unusable for
exactly the people who use it most. Writes are management-gated.

Scoping is by organization on every route, and a tree outside the caller's is
`404`, never `403`: the existence of another tenant's tree is not ours to
disclose.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from web_api.db.models import Company, SpendCategory, SpendTree
from ..deps import TenantScope, get_session, require_management, tenant_scope
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
)
from ..spend_trees import importer, service

router = APIRouter(prefix="/api/v1", tags=["spend-trees"])

_STATUS_BY_CODE = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "conflict": status.HTTP_409_CONFLICT,
    "invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _http(error: service.SpendTreeError) -> HTTPException:
    """Map a service rule violation to its status code.

    One mapping, in one place: the service states the rule and its severity, and
    every route reports it identically — the same reason `_entry_conditions()`
    is shared across the entry listings.
    """
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
    """One tree with all its nodes.

    The whole tree in one response on purpose: it is hundreds of nodes at most,
    and the selector's column navigation and search are both instant only if the
    client already holds it.
    """
    return _tree_read(session, _get_tree(session, scope, tree_id), with_nodes=True)


@router.post("/spend-trees/default", response_model=SpendTreeDetailRead)
def ensure_default_spend_tree(
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> SpendTreeDetailRead:
    """The organization's copy of the platform template, created if absent.

    Idempotent, and `200` rather than `201` because the usual answer is "here is
    the one you already have". Exists because copy-on-first-use otherwise has
    exactly one trigger — creating a company — which leaves an organization that
    predates spend trees with no way to obtain the default at all.

    Declared above `POST /spend-trees` so the literal path is matched before the
    generic one.
    """
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
        session.rollback()
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
        session.rollback()
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
    """Soft-archive. Refused while a company still categorizes against it."""
    tree = _get_tree(session, scope, tree_id)
    try:
        service.archive_tree(session, tree)
    except service.SpendTreeError as error:
        session.rollback()
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
    """Delete a tree and its nodes.

    Refused while a company is assigned. When categorized lines point at its
    nodes, refused with `409` and the count until `confirm=true` — those lines
    keep every stored level and simply become stale, but that is the caller's
    to accept.
    """
    tree = _get_tree(session, scope, tree_id)
    try:
        stale = service.delete_tree(session, tree, confirm=confirm)
    except service.SpendTreeError as error:
        session.rollback()
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
    """Load a CSV of `level_1..level_4` (+ `description`, `code`) into a tree.

    Validated wholly before anything is written; a file with one bad row is
    rejected in full with a per-row report and leaves the tree untouched.

    A `replace` that would remove nodes categorized lines point at is refused
    with `409` and the affected count until the caller passes `confirm=true` —
    the removal is not destructive to the lines (they keep every stored level),
    but it does leave that many needing a fresh decision, and that is the
    caller's to accept.
    """
    tree = _get_tree(session, scope, tree_id)
    try:
        plan = importer.plan_import(session, tree, content, mode=mode)
    except service.SpendTreeError as error:
        session.rollback()
        raise _http(error) from error

    if plan.affected_lines and not confirm:
        session.rollback()
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


# -- Nodes -------------------------------------------------------------------


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
        session.rollback()
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
        # `parent_id: None` means "move to the top level", so a move is applied
        # only when the field was actually sent — the reason this reads
        # `model_fields_set` rather than testing for None.
        if "parent_id" in body.model_fields_set:
            service.move_node(session, node, body.parent_id)
        service.update_node(
            session, node, name=body.name, code=body.code,
            description=body.description, sort_order=body.sort_order,
        )
    except service.SpendTreeError as error:
        session.rollback()
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
    """Delete a leaf. Lines pointing at it keep their levels and go stale."""
    try:
        node = service.get_node(session, node_id, scope.organization_id)
        stale = service.delete_node(session, node)
    except service.SpendTreeError as error:
        session.rollback()
        raise _http(error) from error
    session.commit()
    return SpendTreeDeleteResult(stale_lines=stale)
