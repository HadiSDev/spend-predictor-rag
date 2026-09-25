"""The only writer of ``SpendCategory``."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from ..db.models import Company, InvoiceLine, SpendCategory, SpendTree
from ..db.models.enums import SpendTreeSource
from .template import DEFAULT_TEMPLATE, TEMPLATE_MAX_DEPTH, TEMPLATE_NAME, TEMPLATE_VERSION

MAX_SUPPORTED_DEPTH = 4

_LEVEL_FIELDS = ("level_1", "level_2", "level_3", "level_4")


class SpendTreeError(Exception):
    """A spend-tree rule was violated."""

    def __init__(self, message: str, *, code: str = "invalid") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _apply_path(node: SpendCategory, path: tuple[str, ...]) -> None:
    """Write a node's depth and its materialized level path."""
    node.depth = len(path)
    for index, field in enumerate(_LEVEL_FIELDS):
        setattr(node, field, path[index] if index < len(path) else None)


def node_path(node: SpendCategory) -> tuple[str, ...]:
    """The node's materialized path as a tuple, trailing nulls dropped."""
    values = [getattr(node, field) for field in _LEVEL_FIELDS]
    path: list[str] = []
    for value in values:
        if value is None:
            break
        path.append(value)
    return tuple(path)


def _children_by_parent(session: Session, tree_id: str) -> dict[str | None, list[SpendCategory]]:
    nodes = session.exec(
        select(SpendCategory).where(SpendCategory.spend_tree_id == tree_id)
    ).all()
    grouped: dict[str | None, list[SpendCategory]] = {}
    for node in nodes:
        grouped.setdefault(node.parent_id, []).append(node)
    return grouped


def _rewrite_paths(session: Session, tree_id: str, root: SpendCategory | None = None) -> None:
    """Rebuild materialized paths from parentage, for a subtree or a whole tree."""
    grouped = _children_by_parent(session, tree_id)

    if root is None:
        frontier = [(node, (node.name,)) for node in grouped.get(None, [])]
    else:
        parent_path = ()
        if root.parent_id is not None:
            parent = session.get(SpendCategory, root.parent_id)
            parent_path = node_path(parent) if parent else ()
        frontier = [(root, parent_path + (root.name,))]

    while frontier:
        node, path = frontier.pop()
        _apply_path(node, path)
        session.add(node)
        for child in grouped.get(node.id, []):
            frontier.append((child, path + (child.name,)))


def _subtree_depth(session: Session, tree_id: str, root: SpendCategory) -> int:
    """How many levels the subtree under ``root`` spans, ``root`` counting as 1."""
    grouped = _children_by_parent(session, tree_id)
    deepest = 1
    frontier = [(root, 1)]
    while frontier:
        node, level = frontier.pop()
        deepest = max(deepest, level)
        for child in grouped.get(node.id, []):
            frontier.append((child, level + 1))
    return deepest


def _assert_no_cycle(session: Session, node: SpendCategory, new_parent: SpendCategory) -> None:
    cursor: SpendCategory | None = new_parent
    seen = 0
    while cursor is not None:
        if cursor.id == node.id:
            raise SpendTreeError("A node cannot be moved beneath itself.")
        if cursor.parent_id is None:
            return
        seen += 1
        if seen > MAX_SUPPORTED_DEPTH + 1:
            raise SpendTreeError("The tree contains a cycle.", code="conflict")
        cursor = session.get(SpendCategory, cursor.parent_id)


def get_tree(session: Session, tree_id: str, organization_id: str) -> SpendTree:
    """A tree of the caller's organization, or ``not_found``."""
    tree = session.get(SpendTree, tree_id)
    if tree is None or tree.organization_id != organization_id:
        raise SpendTreeError("Spend tree not found.", code="not_found")
    return tree


def get_node(session: Session, node_id: str, organization_id: str) -> SpendCategory:
    node = session.get(SpendCategory, node_id)
    if node is None:
        raise SpendTreeError("Spend category not found.", code="not_found")
    get_tree(session, node.spend_tree_id, organization_id)
    return node


def tree_nodes(session: Session, tree_id: str) -> list[SpendCategory]:
    """A tree's nodes, ordered so a client can build the hierarchy in one pass."""
    return list(
        session.exec(
            select(SpendCategory)
            .where(SpendCategory.spend_tree_id == tree_id)
            .order_by(
                SpendCategory.depth,
                SpendCategory.sort_order,
                SpendCategory.name,
            )
        ).all()
    )


def _sibling_exists(session: Session, tree_id: str, parent_id: str | None, name: str,
                    exclude_id: str | None = None) -> bool:
    rows = session.exec(
        select(SpendCategory).where(
            SpendCategory.spend_tree_id == tree_id,
            SpendCategory.parent_id == parent_id,
            SpendCategory.name == name,
        )
    ).all()
    return any(row.id != exclude_id for row in rows)


def _next_sort_order(session: Session, tree_id: str, parent_id: str | None) -> int:
    siblings = session.exec(
        select(SpendCategory).where(
            SpendCategory.spend_tree_id == tree_id,
            SpendCategory.parent_id == parent_id,
        )
    ).all()
    return max((s.sort_order for s in siblings), default=-1) + 1


def create_tree(
    session: Session,
    organization_id: str,
    name: str,
    max_depth: int = 3,
    source: SpendTreeSource = SpendTreeSource.CUSTOM,
    template_version: str | None = None,
) -> SpendTree:
    if max_depth not in (3, MAX_SUPPORTED_DEPTH):
        raise SpendTreeError("A spend tree must be 3 or 4 levels deep.")
    if source == SpendTreeSource.DEFAULT_TEMPLATE and max_depth != TEMPLATE_MAX_DEPTH:
        raise SpendTreeError(
            f"The default template is {TEMPLATE_MAX_DEPTH} levels deep."
        )
    tree = SpendTree(
        organization_id=organization_id,
        name=name.strip(),
        max_depth=max_depth,
        source=source,
        template_version=template_version,
    )
    session.add(tree)
    session.flush()
    return tree


def update_tree(
    session: Session,
    tree: SpendTree,
    name: str | None = None,
    max_depth: int | None = None,
) -> SpendTree:
    if name is not None:
        tree.name = name.strip()
    if max_depth is not None and max_depth != tree.max_depth:
        if max_depth not in (3, MAX_SUPPORTED_DEPTH):
            raise SpendTreeError("A spend tree must be 3 or 4 levels deep.")
        if tree.source == SpendTreeSource.DEFAULT_TEMPLATE:
            raise SpendTreeError(
                "The default-template tree is fixed at three levels. Clone it to go deeper."
            )
        deepest = max((n.depth for n in tree_nodes(session, tree.id)), default=0)
        if max_depth < deepest:
            raise SpendTreeError(
                f"This tree has nodes at level {deepest}; empty them before "
                f"lowering the maximum depth to {max_depth}."
            )
        tree.max_depth = max_depth
    session.add(tree)
    return tree


def archive_tree(session: Session, tree: SpendTree) -> SpendTree:
    """Soft-archive."""
    assigned = session.exec(
        select(Company).where(Company.spend_tree_id == tree.id)
    ).all()
    if assigned:
        names = ", ".join(sorted(c.name for c in assigned))
        raise SpendTreeError(
            f"This tree is in use by {names}. Assign those companies another tree first.",
            code="conflict",
        )
    tree.archived_at = datetime.now(timezone.utc)
    session.add(tree)
    return tree


def tree_line_references(session: Session, tree_id: str) -> list[InvoiceLine]:
    """Invoice lines whose accepted category points at a node of this tree."""
    node_ids = [node.id for node in tree_nodes(session, tree_id)]
    return lines_referencing(session, node_ids)


def delete_tree(session: Session, tree: SpendTree, confirm: bool = False) -> int:
    """Delete a tree and its nodes."""
    assigned = session.exec(
        select(Company).where(Company.spend_tree_id == tree.id)
    ).all()
    if assigned:
        names = ", ".join(sorted(c.name for c in assigned))
        raise SpendTreeError(
            f"This tree is in use by {names}. Assign those companies another tree first.",
            code="conflict",
        )

    affected = tree_line_references(session, tree.id)
    if affected and not confirm:
        raise SpendTreeError(
            f"{len(affected)} invoice line(s) are categorized against this tree. "
            "They keep their categories on record but will need reviewing.",
            code="conflict",
        )

    for line in affected:
        line.spend_category_id = None
        session.add(line)
    for node in sorted(tree_nodes(session, tree.id), key=lambda n: n.depth, reverse=True):
        session.delete(node)
    session.delete(tree)
    return len(affected)


def clone_tree(session: Session, source: SpendTree, name: str, max_depth: int | None = None) -> SpendTree:
    """Copy a tree's nodes into a new custom tree in the same organization."""
    target_depth = max_depth if max_depth is not None else source.max_depth
    clone = create_tree(
        session, source.organization_id, name, max_depth=target_depth,
        source=SpendTreeSource.CUSTOM,
    )

    originals = tree_nodes(session, source.id)
    deepest = max((n.depth for n in originals), default=0)
    if deepest > target_depth:
        raise SpendTreeError(
            f"The source tree has nodes at level {deepest}, deeper than {target_depth}."
        )

    id_map: dict[str, str] = {}
    for original in sorted(originals, key=lambda n: n.depth):
        copy = SpendCategory(
            spend_tree_id=clone.id,
            parent_id=id_map.get(original.parent_id) if original.parent_id else None,
            depth=original.depth,
            name=original.name,
            code=original.code,
            sort_order=original.sort_order,
            description=original.description,
            level_1=original.level_1,
            level_2=original.level_2,
            level_3=original.level_3,
            level_4=original.level_4,
        )
        session.add(copy)
        session.flush()
        id_map[original.id] = copy.id
    return clone


def add_node(
    session: Session,
    tree: SpendTree,
    name: str,
    parent_id: str | None = None,
    code: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
) -> SpendCategory:
    name = (name or "").strip()
    if not name:
        raise SpendTreeError("A spend category needs a name.")

    parent: SpendCategory | None = None
    if parent_id is not None:
        parent = session.get(SpendCategory, parent_id)
        if parent is None or parent.spend_tree_id != tree.id:
            raise SpendTreeError("The parent category is not in this tree.", code="not_found")

    depth = 1 if parent is None else parent.depth + 1
    if depth > tree.max_depth:
        raise SpendTreeError(
            f"This tree is {tree.max_depth} levels deep; a level {depth} category "
            "cannot be added."
        )
    if _sibling_exists(session, tree.id, parent_id, name):
        raise SpendTreeError(
            f"'{name}' already exists under this parent.", code="conflict"
        )
    if code and _code_taken(session, tree.id, code):
        raise SpendTreeError(f"Code '{code}' is already used in this tree.", code="conflict")

    node = SpendCategory(
        spend_tree_id=tree.id,
        parent_id=parent_id,
        name=name,
        code=code or None,
        description=description,
        sort_order=sort_order if sort_order is not None
        else _next_sort_order(session, tree.id, parent_id),
    )
    path = (node_path(parent) if parent else ()) + (name,)
    _apply_path(node, path)
    session.add(node)
    session.flush()
    return node


def _code_taken(session: Session, tree_id: str, code: str, exclude_id: str | None = None) -> bool:
    rows = session.exec(
        select(SpendCategory).where(
            SpendCategory.spend_tree_id == tree_id,
            SpendCategory.code == code,
        )
    ).all()
    return any(row.id != exclude_id for row in rows)


def rename_node(session: Session, node: SpendCategory, name: str) -> SpendCategory:
    name = (name or "").strip()
    if not name:
        raise SpendTreeError("A spend category needs a name.")
    if name == node.name:
        return node
    if _sibling_exists(session, node.spend_tree_id, node.parent_id, name, exclude_id=node.id):
        raise SpendTreeError(f"'{name}' already exists under this parent.", code="conflict")
    node.name = name
    session.add(node)
    session.flush()
    _rewrite_paths(session, node.spend_tree_id, node)
    return node


def update_node(
    session: Session,
    node: SpendCategory,
    name: str | None = None,
    code: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
) -> SpendCategory:
    if code is not None:
        stripped = code.strip() or None
        if stripped and _code_taken(session, node.spend_tree_id, stripped, exclude_id=node.id):
            raise SpendTreeError(
                f"Code '{stripped}' is already used in this tree.", code="conflict"
            )
        node.code = stripped
    if description is not None:
        node.description = description or None
    if sort_order is not None:
        node.sort_order = sort_order
    session.add(node)
    if name is not None:
        rename_node(session, node, name)
    return node


def move_node(
    session: Session, node: SpendCategory, new_parent_id: str | None
) -> SpendCategory:
    if new_parent_id == node.parent_id:
        return node

    tree = session.get(SpendTree, node.spend_tree_id)
    parent: SpendCategory | None = None
    if new_parent_id is not None:
        parent = session.get(SpendCategory, new_parent_id)
        if parent is None or parent.spend_tree_id != node.spend_tree_id:
            raise SpendTreeError("The parent category is not in this tree.", code="not_found")
        _assert_no_cycle(session, node, parent)

    new_depth = 1 if parent is None else parent.depth + 1
    span = _subtree_depth(session, node.spend_tree_id, node)
    if new_depth + span - 1 > tree.max_depth:
        raise SpendTreeError(
            f"Moving this category there would put its children below level "
            f"{tree.max_depth}."
        )
    if _sibling_exists(session, node.spend_tree_id, new_parent_id, node.name, exclude_id=node.id):
        raise SpendTreeError(
            f"'{node.name}' already exists under that parent.", code="conflict"
        )

    node.parent_id = new_parent_id
    node.sort_order = _next_sort_order(session, node.spend_tree_id, new_parent_id)
    session.add(node)
    session.flush()
    _rewrite_paths(session, node.spend_tree_id, node)
    return node


def lines_referencing(session: Session, node_ids: list[str]) -> list[InvoiceLine]:
    """Invoice lines whose accepted category points at one of these nodes."""
    if not node_ids:
        return []
    return list(
        session.exec(
            select(InvoiceLine).where(InvoiceLine.spend_category_id.in_(node_ids))
        ).all()
    )


def delete_node(session: Session, node: SpendCategory) -> int:
    """Delete a leaf."""
    children = session.exec(
        select(SpendCategory).where(SpendCategory.parent_id == node.id)
    ).all()
    if children:
        raise SpendTreeError(
            f"This category has {len(children)} child categories. Delete or move "
            "them first.",
            code="conflict",
        )

    affected = lines_referencing(session, [node.id])
    for line in affected:
        line.spend_category_id = None
        session.add(line)
    session.delete(node)
    return len(affected)


def seed_template(session: Session, tree: SpendTree) -> None:
    """Write the platform template's nodes into an empty tree."""
    by_path: dict[tuple[str, ...], SpendCategory] = {}
    for order, spec in enumerate(DEFAULT_TEMPLATE):
        parent = by_path.get(spec.path[:-1]) if spec.depth > 1 else None
        node = SpendCategory(
            spend_tree_id=tree.id,
            parent_id=parent.id if parent else None,
            name=spec.name,
            code=spec.code,
            description=spec.description,
            sort_order=order,
        )
        _apply_path(node, spec.path)
        session.add(node)
        session.flush()
        by_path[spec.path] = node


def ensure_default_tree(session: Session, organization_id: str) -> SpendTree:
    """The organization's copy of the default template, created if absent."""
    existing = session.exec(
        select(SpendTree).where(
            SpendTree.organization_id == organization_id,
            SpendTree.source == SpendTreeSource.DEFAULT_TEMPLATE,
            SpendTree.archived_at.is_(None),
        ).order_by(SpendTree.created_at, SpendTree.id)
    ).first()
    if existing is not None:
        return existing

    tree = create_tree(
        session,
        organization_id,
        TEMPLATE_NAME,
        max_depth=TEMPLATE_MAX_DEPTH,
        source=SpendTreeSource.DEFAULT_TEMPLATE,
        template_version=TEMPLATE_VERSION,
    )
    seed_template(session, tree)
    return tree
