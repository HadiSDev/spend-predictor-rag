"""Which fields a human has settled, and what that protects them from.

`Invoice.verified_fields` and `InvoiceLine.verified_fields` hold field names a
person has reviewed. The list is what stops an automated write — a re-sync, a
re-extraction — from silently replacing a value someone decided was right.

**Per field, not per row**, and that is the whole design. A row-level "verified"
flag would freeze the invoice against the ERP entirely: a reviewer who corrects
a typo'd invoice number would also stop a genuine later re-posting of the total
from ever reaching us. A field list keeps the sync doing its job everywhere a
human has not spoken.

These helpers live in the domain because both sides need them and only one may
import the other: `web_api`'s routers mark fields verified, and `ai_api`'s sync
runner reads the marks through the one-way `ai_api → web_api` dependency.

The list is stored sorted and deduped so a diff of two rows is stable and an
audit trail never shows a "change" that was only a reordering.
"""
from __future__ import annotations

from typing import Iterable, Protocol


class _HasVerifiedFields(Protocol):
    """Any row carrying the marker — `Invoice` or `InvoiceLine`."""

    verified_fields: list[str]


def is_verified(row: _HasVerifiedFields, field: str) -> bool:
    """Has a human settled this field on this row?"""
    return field in (row.verified_fields or ())


def mark_verified(row: _HasVerifiedFields, fields: Iterable[str]) -> None:
    """Record that a human settled ``fields``, keeping what was settled before.

    A **new list** is assigned rather than the existing one mutated: SQLAlchemy
    tracks a JSON column by identity, so an in-place ``.append()`` is not seen as
    a change and the write is silently dropped. This is the single most likely
    way for this feature to fail in production, which is why nothing else in the
    codebase touches these lists directly.
    """
    row.verified_fields = sorted(set(row.verified_fields or ()) | set(fields))


def clear_verified(row: _HasVerifiedFields, fields: Iterable[str]) -> None:
    """Drop ``fields`` from the settled set.

    Used by the sync runner's ``--hard-reset``, which overwrites a human's value
    with the ERP's: the row must not go on claiming a field is verified at a
    value it no longer holds.
    """
    row.verified_fields = sorted(set(row.verified_fields or ()) - set(fields))
