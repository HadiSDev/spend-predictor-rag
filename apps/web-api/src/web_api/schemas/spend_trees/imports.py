"""The outcome of importing a spend tree from CSV."""
from __future__ import annotations

from pydantic import BaseModel


class SpendTreeImportError(BaseModel):
    """One rejected row, addressed by its line number in the uploaded file."""

    line: int
    message: str


class SpendTreeImportResult(BaseModel):
    """What an import did, or — with `confirm_required` — what it would do."""

    created: int = 0
    updated: int = 0
    removed: int = 0
    stale_lines: int = 0
