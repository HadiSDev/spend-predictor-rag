"""Shared field types and response envelopes."""
from __future__ import annotations

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel


T = TypeVar("T")


def _iso_4217(value: str) -> str:
    """Validate and normalize a currency code."""
    code = value.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("must be a three-letter ISO 4217 currency code, e.g. 'DKK'")
    return code


CurrencyCode = Annotated[str, AfterValidator(_iso_4217)]
CurrencyMode = Literal["base", "original"]


class Page(BaseModel, Generic[T]):
    """A paginated result envelope."""

    items: list[T]
    page: int
    page_size: int
    total: int


class Report(BaseModel, Generic[T]):
    """Envelope for a small aggregate report (no pagination)."""

    rows: list[T]
