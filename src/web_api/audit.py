"""Shared audit-trail helpers used by both the AI write path and human actions.

These live in ``web_api`` (the domain) so the ai_api sync runner can reach them
through the one-way ``ai_api → web_api`` dependency and record audit entries in
the same shape a human verification does. Append-only: helpers only ever add
``AuditLog`` rows.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlmodel import Session

from .db.models import AuditLog
from .db.models.audit_log import SYSTEM_ACTOR

# Auditable fields on an invoice line, in a stable order for deterministic diffs.
LINE_AUDIT_FIELDS = (
    "level_1", "level_2", "level_3", "account_code", "account_name",
    "confidence", "rationale", "spend_category_id", "status",
)


def _norm(value: Any) -> Any:
    """Normalize a value for diffing/JSON storage (Decimal → str, else as-is)."""
    if value is None:
        return None
    # Enums (e.g. the status vocab) → their raw string value.
    if isinstance(value, Enum):
        return value.value
    # Decimal isn't JSON-serializable and compares awkwardly; store as a string.
    if value.__class__.__name__ == "Decimal":
        return str(value)
    return value


def diff_changes(old: dict[str, Any], new: dict[str, Any], fields) -> list[dict]:
    """Build a list of ``{field, old, new}`` for fields whose value changed."""
    changes: list[dict] = []
    for field in fields:
        old_v = _norm(old.get(field))
        new_v = _norm(new.get(field))
        if old_v != new_v:
            changes.append({"field": field, "old": old_v, "new": new_v})
    return changes


def record_audit(
    session: Session,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str = SYSTEM_ACTOR,
    changes: list[dict] | None = None,
) -> AuditLog:
    """Append an audit entry. Caller commits as part of its own transaction.

    `created_at` is stamped here in Python (microsecond resolution) rather than
    left to the column's `server_default=func.now()`: SQLite's `CURRENT_TIMESTAMP`
    only has *second* resolution, so two rows written by the same request (e.g.
    ai_categorize + a same-second verify) would otherwise tie, and a voucher-wide
    feed ordered `created_at DESC` needs those rows to stay ordered the way they
    were written.
    """
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        changes=changes or [],
        created_at=datetime.now(timezone.utc),
    )
    session.add(entry)
    return entry
