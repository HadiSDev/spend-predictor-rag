"""Shared audit-trail helpers used by both the AI write path and human actions."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlmodel import Session

from .db.models import AuditLog
from .db.models.audit_log import SYSTEM_ACTOR

LINE_AUDIT_FIELDS = (
    "level_1", "level_2", "level_3", "level_4", "account_code", "account_name",
    "confidence", "rationale", "spend_category_id", "status",
)

LINE_VALUE_AUDIT_FIELDS = (
    "item_name", "description", "quantity", "unit", "unit_price", "amount",
)

LINE_BASE_FX_FIELDS = (
    "base_currency", "base_amount", "fx_rate", "fx_rate_date",
)

INVOICE_AUDIT_FIELDS = (
    "document_invoice_number", "invoice_number", "invoice_date", "currency",
    "total", "tax", "vendor_id",
    "supplier_name", "supplier_country_code", "supplier_vat_number",
)

INVOICE_BASE_FX_FIELDS = (
    "base_currency", "base_total", "base_tax", "fx_rate", "fx_rate_date",
)


def _norm(value: Any) -> Any:
    """Normalize a value for diffing/JSON storage (Decimal → str, else as-is)."""
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if value.__class__.__name__ == "Decimal":
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


audit_value = _norm


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
    """Append an audit entry."""
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        changes=changes or [],
    )
    session.add(entry)
    return entry
