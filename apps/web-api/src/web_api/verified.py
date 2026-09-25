"""Which fields a human has settled, and what that protects them from."""
from __future__ import annotations

from typing import Iterable, Protocol


class _HasVerifiedFields(Protocol):
    """Any row carrying the marker — `Invoice` or `InvoiceLine`."""

    verified_fields: list[str]


def is_verified(row: _HasVerifiedFields, field: str) -> bool:
    """Has a human settled this field on this row?"""
    return field in (row.verified_fields or ())


def mark_verified(row: _HasVerifiedFields, fields: Iterable[str]) -> None:
    """Record that a human settled ``fields``, keeping what was settled before."""
    row.verified_fields = sorted(set(row.verified_fields or ()) | set(fields))


def clear_verified(row: _HasVerifiedFields, fields: Iterable[str]) -> None:
    """Drop ``fields`` from the settled set."""
    row.verified_fields = sorted(set(row.verified_fields or ()) - set(fields))
