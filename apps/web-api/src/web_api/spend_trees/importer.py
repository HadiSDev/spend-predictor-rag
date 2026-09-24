"""CSV import: a customer's existing taxonomy, in one file.

The governing rule is **validate wholly, then write wholly**. A file with one
bad row is rejected in full and the tree is left exactly as it was. A
half-loaded taxonomy is worse than none: the missing half is invisible, and
every categorization that lands in the gap looks like a considered decision.

Columns: ``level_1``, ``level_2``, ``level_3``, ``level_4``, ``description``,
optional ``code``. A row states a **full path**, so interior nodes are implied
by their descendants and materialized here — that is how spreadsheets of
taxonomies are actually written, one leaf per line.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from sqlmodel import Session, select

from ..db.models import InvoiceLine, SpendCategory, SpendTree
from .service import SpendTreeError, node_path, tree_nodes

_LEVEL_COLUMNS = ("level_1", "level_2", "level_3", "level_4")

#: Import modes. ``merge`` adds and updates; ``replace`` also removes nodes the
#: file does not mention.
MERGE = "merge"
REPLACE = "replace"


@dataclass(frozen=True)
class RowError:
    """One rejected row, addressed by its line number *in the file*.

    The file's line number, not the row index: a user fixes a spreadsheet by
    going to a line, and an off-by-header index sends them to the wrong one.
    """

    line: int
    message: str


class ImportRejected(SpendTreeError):
    """The file did not validate. Nothing was written."""

    def __init__(self, errors: list[RowError]) -> None:
        super().__init__(
            f"{len(errors)} row(s) could not be imported; nothing was changed.",
            code="invalid",
        )
        self.errors = errors


@dataclass(frozen=True)
class ParsedRow:
    path: tuple[str, ...]
    code: str | None
    description: str | None
    line: int


@dataclass
class ImportPlan:
    """What an import would do, computed before anything is written."""

    rows: list[ParsedRow]
    #: Every path the file implies, interior nodes included, shallowest first.
    paths: list[tuple[str, ...]]
    #: Existing nodes whose path the file does not mention (``replace`` only).
    removed: list[SpendCategory]
    #: Invoice lines pointing at a node in ``removed``.
    affected_lines: list[InvoiceLine]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def parse(content: str) -> tuple[list[ParsedRow], list[RowError]]:
    """Parse the file. Returns rows and the errors that are visible per row."""
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None:
        return [], [RowError(1, "The file is empty.")]

    headers = {(name or "").strip().lower() for name in reader.fieldnames}
    if not headers & set(_LEVEL_COLUMNS):
        return [], [
            RowError(
                1,
                "No level columns found. Expected at least one of "
                + ", ".join(_LEVEL_COLUMNS)
                + ".",
            )
        ]

    rows: list[ParsedRow] = []
    errors: list[RowError] = []
    seen_paths: dict[tuple[str, ...], int] = {}
    seen_codes: dict[str, int] = {}

    for index, raw in enumerate(reader):
        line = index + 2  # 1-based, past the header row
        values = {key: _clean(raw.get(key)) for key in _LEVEL_COLUMNS}
        levels = [values[key] for key in _LEVEL_COLUMNS]

        if all(value is None for value in levels):
            continue  # a blank line in a spreadsheet is not an error

        # A gap means the row does not describe a path: `level_3` with no
        # `level_2` has no parent to hang from.
        path: list[str] = []
        gap = False
        for depth, value in enumerate(levels, start=1):
            if value is None:
                if any(deeper is not None for deeper in levels[depth:]):
                    gap = True
                break
            path.append(value)
        if gap:
            errors.append(RowError(
                line,
                "This row skips a level — every level above the deepest one must "
                "be filled in.",
            ))
            continue

        key = tuple(path)
        if key in seen_paths:
            errors.append(RowError(
                line, f"Duplicate of the category on line {seen_paths[key]}."
            ))
            continue
        seen_paths[key] = line

        code = _clean(raw.get("code"))
        if code is not None:
            if code in seen_codes:
                errors.append(RowError(
                    line, f"Code '{code}' is already used on line {seen_codes[code]}."
                ))
                continue
            seen_codes[code] = line

        rows.append(ParsedRow(
            path=key, code=code, description=_clean(raw.get("description")), line=line
        ))

    if not rows and not errors:
        errors.append(RowError(1, "The file contains no categories."))
    return rows, errors


def plan_import(
    session: Session, tree: SpendTree, content: str, mode: str = MERGE
) -> ImportPlan:
    """Validate the whole file against the tree. Raises before any write.

    Nothing here touches the session's write path — the caller gets a plan it can
    show a user (how many rows, how many nodes would go, how many lines would be
    left stale) and only then applies it.
    """
    if mode not in (MERGE, REPLACE):
        raise SpendTreeError(f"Unknown import mode '{mode}'.")

    rows, errors = parse(content)

    for row in rows:
        if len(row.path) > tree.max_depth:
            errors.append(RowError(
                row.line,
                f"This category is {len(row.path)} levels deep; this tree allows "
                f"{tree.max_depth}.",
            ))

    if errors:
        raise ImportRejected(sorted(errors, key=lambda e: (e.line, e.message)))

    # Interior nodes the file only implies. A taxonomy spreadsheet lists leaves.
    implied: set[tuple[str, ...]] = set()
    for row in rows:
        for length in range(1, len(row.path) + 1):
            implied.add(row.path[:length])
    paths = sorted(implied, key=lambda p: (len(p), p))

    existing = tree_nodes(session, tree.id)
    removed: list[SpendCategory] = []
    if mode == REPLACE:
        keep = set(paths)
        removed = [node for node in existing if node_path(node) not in keep]

    affected = _lines_for(session, [node.id for node in removed])
    return ImportPlan(rows=rows, paths=paths, removed=removed, affected_lines=affected)


def _lines_for(session: Session, node_ids: list[str]) -> list[InvoiceLine]:
    if not node_ids:
        return []
    return list(
        session.exec(
            select(InvoiceLine).where(InvoiceLine.spend_category_id.in_(node_ids))
        ).all()
    )


def apply_import(session: Session, tree: SpendTree, plan: ImportPlan) -> dict:
    """Write a validated plan. Adds to the caller's session; does not commit.

    Nodes are keyed by path, so a re-import of the same file updates in place
    and an ``InvoiceLine`` pointing at a node keeps pointing at it. Removal
    clears the pointer and leaves the line's stored levels — the same rule a
    reassignment follows.
    """
    by_path = {node_path(node): node for node in tree_nodes(session, tree.id)}
    row_by_path = {row.path: row for row in plan.rows}

    created = 0
    updated = 0
    for order, path in enumerate(plan.paths):
        row = row_by_path.get(path)
        node = by_path.get(path)
        parent = by_path.get(path[:-1]) if len(path) > 1 else None

        if node is None:
            node = SpendCategory(
                spend_tree_id=tree.id,
                parent_id=parent.id if parent else None,
                depth=len(path),
                name=path[-1],
                code=row.code if row else None,
                description=row.description if row else None,
                sort_order=order,
            )
            for index, field in enumerate(_LEVEL_COLUMNS):
                setattr(node, field, path[index] if index < len(path) else None)
            session.add(node)
            session.flush()
            by_path[path] = node
            created += 1
        elif row is not None:
            # Only a row the file actually carried may overwrite a node's own
            # fields; an implied interior node states nothing about them.
            node.code = row.code
            node.description = row.description
            node.sort_order = order
            session.add(node)
            updated += 1

    stale = 0
    for line in plan.affected_lines:
        line.spend_category_id = None
        session.add(line)
        stale += 1
    # Deepest first, so a parent is never deleted while a child still points at it.
    for node in sorted(plan.removed, key=lambda n: n.depth, reverse=True):
        session.delete(node)

    return {
        "created": created,
        "updated": updated,
        "removed": len(plan.removed),
        "stale_lines": stale,
    }
