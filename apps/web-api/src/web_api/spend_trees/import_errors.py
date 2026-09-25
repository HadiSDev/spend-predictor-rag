"""Why a spend-tree CSV import was rejected."""
from __future__ import annotations

from dataclasses import dataclass

from .service import SpendTreeError


@dataclass(frozen=True)
class RowError:
    """One rejected row, addressed by its line number *in the file*."""

    line: int
    message: str


class ImportRejected(SpendTreeError):
    """The file did not validate."""

    def __init__(self, errors: list[RowError]) -> None:
        super().__init__(
            f"{len(errors)} row(s) could not be imported; nothing was changed.",
            code="invalid",
        )
        self.errors = errors
