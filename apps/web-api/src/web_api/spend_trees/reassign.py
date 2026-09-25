"""What happens to a company's categorized lines when its spend tree changes."""
from __future__ import annotations

from sqlalchemy import or_
from sqlmodel import Session, select

from ..audit import record_audit
from ..db.models import InvoiceLine, SpendCategory
from ..db.models.audit_log import SYSTEM_ACTOR
from .service import node_path

REASSIGN_ACTION = "spend_tree_reassigned"

_LEVEL_FIELDS = ("level_1", "level_2", "level_3", "level_4")


def _line_path(line: InvoiceLine) -> tuple[str, ...]:
    path: list[str] = []
    for field in _LEVEL_FIELDS:
        value = getattr(line, field)
        if value is None:
            break
        path.append(value)
    return tuple(path)


def reassign_company_tree(
    session: Session,
    company_id: str,
    from_tree_id: str | None,
    to_tree_id: str | None,
) -> int:
    """Re-point or clear a company's line categories after a tree change."""
    lines = session.exec(
        select(InvoiceLine).where(
            InvoiceLine.company_id == company_id,
            InvoiceLine.spend_category_id.is_not(None),
        )
    ).all()
    if not lines:
        return 0

    by_path: dict[tuple[str, ...], str] = {}
    if to_tree_id is not None:
        for node in session.exec(
            select(SpendCategory).where(SpendCategory.spend_tree_id == to_tree_id)
        ).all():
            by_path[node_path(node)] = node.id

    stale = 0
    for line in lines:
        previous = line.spend_category_id
        resolved = by_path.get(_line_path(line))
        if resolved == previous:
            continue

        line.spend_category_id = resolved
        session.add(line)
        record_audit(
            session,
            entity_type="invoice_line",
            entity_id=line.id,
            action=REASSIGN_ACTION,
            actor=SYSTEM_ACTOR,
            changes=[
                {"field": "spend_category_id", "old": previous, "new": resolved},
                {"field": "spend_tree_id", "old": from_tree_id, "new": to_tree_id},
            ],
        )
        if resolved is None:
            stale += 1

    return stale


def count_stale(session: Session, company_id: str) -> int:
    """How many of a company's lines carry a decision that resolves to nothing."""
    return len(
        session.exec(
            select(InvoiceLine).where(
                InvoiceLine.company_id == company_id,
                or_(InvoiceLine.level_1.is_not(None), InvoiceLine.level_2.is_not(None)),
                InvoiceLine.spend_category_id.is_(None),
            )
        ).all()
    )
