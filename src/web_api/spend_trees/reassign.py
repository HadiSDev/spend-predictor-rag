"""What happens to a company's categorized lines when its spend tree changes.

The rule, in one sentence: **nothing a human or the AI decided is rewritten,
requeued, or deleted** — only the pointer into a tree the company no longer uses
is cleared, and the line becomes visibly stale.

Two things follow from that and both are deliberate:

- **Re-resolution is exact-match only.** A line whose stored path equals a node's
  path in the new tree, name for name, keeps a resolving category. Anything
  looser is the guessing the sync's derived entry→line link explicitly refuses,
  and getting it wrong silently reassigns a verified category to a different
  node.
- **It runs synchronously, inside the caller's transaction.** The caller must
  learn the consequence at the moment they cause it — a dialog reading "this
  leaves 412 lines needing review" is the whole safety of the feature. A
  company's line count is bounded by its ledger; if this ever becomes slow the
  answer is a job with a progress endpoint, not silent asynchrony.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlmodel import Session, select

from ..audit import record_audit
from ..db.models import InvoiceLine, SpendCategory
from ..db.models.audit_log import SYSTEM_ACTOR
from .service import node_path

#: Recorded as the audit action, so the trail distinguishes "the taxonomy moved"
#: from a human edit or an AI categorization.
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
    """Re-point or clear a company's line categories after a tree change.

    Returns the number of lines left **stale** — categorized, but no longer
    pointing at a node. A line that re-resolves is not counted: nothing about it
    needs review.

    Does not commit; the caller owns the transaction, so the company update and
    its consequence land together or not at all.
    """
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
        # Exact, case-sensitive, whole-path. Never fuzzy — see the module docstring.
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
    """How many of a company's lines carry a decision that resolves to nothing.

    The same predicate ``InvoiceLineRead.category_stale`` uses. Staleness is
    computed, never stored: no second thing to keep in step, and it is correct
    after a reassignment, a node deletion, or a replace import alike.
    """
    return len(
        session.exec(
            select(InvoiceLine).where(
                InvoiceLine.company_id == company_id,
                or_(InvoiceLine.level_1.is_not(None), InvoiceLine.level_2.is_not(None)),
                InvoiceLine.spend_category_id.is_(None),
            )
        ).all()
    )
