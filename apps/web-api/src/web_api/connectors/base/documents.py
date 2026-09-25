"""A document fetched from an ERP."""
from __future__ import annotations

from pydantic import BaseModel


class DocumentPayload(BaseModel):
    """A fetched document's bytes and how to serve them."""

    content: bytes
    media_type: str = "application/pdf"
    filename: str
