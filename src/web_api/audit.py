"""Shared audit-trail helpers used by both the AI write path and human actions.

These live in ``web_api`` (the domain) so the ai_api sync runner can reach them
through the one-way ``ai_api → web_api`` dependency and record audit entries in
the same shape a human verification does. Append-only: helpers only ever add
``AuditLog`` rows.
"""
from __future__ import annotations

from datetime import date, datetime
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

# Auditable fields on an AI-parsed invoice header, in a stable order for
# deterministic diffs. Deliberately the same set `InvoiceUpdate` accepts —
# never a field the ERP posts, since those rows are never reachable here.
INVOICE_AUDIT_FIELDS = (
    "invoice_number", "invoice_date", "currency", "total", "tax", "vendor_id",
)

# The stored conversion, cleared by `update_invoice` whenever a correction
# changes `currency`/`total`/`tax` (see routers/invoices.py). Included in the
# same audit diff as the requested fields so the trail shows the whole effect
# of a correction, not just the part the caller asked for — the same
# precedent as `status` in `LINE_AUDIT_FIELDS`, which also changes as a side
# effect of `verify` rather than something the caller set directly.
INVOICE_BASE_FX_FIELDS = (
    "base_currency", "base_total", "base_tax", "fx_rate", "fx_rate_date",
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
    # date/datetime aren't JSON-serializable either; store as ISO 8601.
    if isinstance(value, (date, datetime)):
        return value.isoformat()
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
    """Append an audit entry. Caller commits as part of its own transaction."""
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        changes=changes or [],
    )
    session.add(entry)
    return entry
