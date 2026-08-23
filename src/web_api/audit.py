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
    "level_1", "level_2", "level_3", "level_4", "account_code", "account_name",
    "confidence", "rationale", "spend_category_id", "status",
)

# What a human may correct on a line, as distinct from its categorization above.
# These go through `PATCH /invoice-lines/{id}`; the categorization goes through
# `verify`, which resolves it against the company's spend tree.
LINE_VALUE_AUDIT_FIELDS = (
    "item_name", "description", "quantity", "unit", "unit_price", "amount",
)

# The line's stored conversion, cleared whenever a correction changes `amount`
# — the value it was derived from. Same rule and same reason as
# `INVOICE_BASE_FX_FIELDS` below.
LINE_BASE_FX_FIELDS = (
    "base_currency", "base_amount", "fx_rate", "fx_rate_date",
)

# Auditable fields on an invoice header, in a stable order for deterministic
# diffs. The same set `InvoiceUpdate` accepts.
#
# Because a correction is applied **in place**, over the ERP's or the
# extractor's own value, this diff is the *only* record of what was originally
# stated — there is no shadow column holding the posted figure. Every field a
# human may correct therefore has to be in this tuple; one omitted here is one
# whose original value is gone for good.
INVOICE_AUDIT_FIELDS = (
    "document_invoice_number", "invoice_number", "invoice_date", "currency",
    "total", "tax", "vendor_id",
    "supplier_name", "supplier_country_code", "supplier_vat_number",
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


#: The same normalization `diff_changes` applies, for callers that build an
#: audit entry without a before/after pair — a deletion, where every value is an
#: `old` and there is no `new` to diff against.
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
