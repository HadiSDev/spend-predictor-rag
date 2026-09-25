"""Extract plain text from a PDF invoice."""
from __future__ import annotations

import io
from pathlib import Path

import pdfplumber


def extract_text(path: str | Path) -> str:
    """Return the concatenated text of all pages, stripped."""
    return _text_of(str(path))


def extract_text_from_bytes(content: bytes) -> str:
    """Return the concatenated text of a PDF held in memory."""
    return _text_of(io.BytesIO(content))


def _text_of(source) -> str:
    parts: list[str] = []
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text)
    return "\n".join(parts).strip()
