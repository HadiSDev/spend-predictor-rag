"""What a document gives a model, and what the model read back from it."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from ..models import LineItem
from .images import DocumentImage


@dataclass(frozen=True)
class DocumentContent:
    """What one document gave us: text, or pictures, never both."""

    text: str | None = None
    images: tuple[DocumentImage, ...] = ()


class ExtractedLines(BaseModel):
    """What one document said, reduced to what an invoice line needs."""

    lines: list[LineItem]
    currency: str | None = None
    invoice_number: str | None = None
    total: float | None = None
    tax: float | None = None
    subtotal: float | None = None
