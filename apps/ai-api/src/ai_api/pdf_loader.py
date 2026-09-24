"""Extract plain text from a PDF invoice."""
from __future__ import annotations

import io
from pathlib import Path

import pdfplumber


def extract_text(path: str | Path) -> str:
    """Return the concatenated text of all pages, stripped.

    Raises if the file cannot be opened/parsed as a PDF; returns "" for a
    valid PDF that contains no extractable text.
    """
    return _text_of(str(path))


def extract_text_from_bytes(content: bytes) -> str:
    """Same, for a PDF held in memory.

    The document stage never writes the scan to disk — there is one copy and it
    lives in the ERP — so it has bytes, not a path.
    """
    return _text_of(io.BytesIO(content))


def _text_of(source) -> str:
    parts: list[str] = []
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text)
    return "\n".join(parts).strip()
