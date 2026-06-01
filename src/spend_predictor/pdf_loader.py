"""Extract plain text from a PDF invoice."""
from __future__ import annotations

from pathlib import Path

import pdfplumber


def extract_text(path: str | Path) -> str:
    """Return the concatenated text of all pages, stripped.

    Raises if the file cannot be opened/parsed as a PDF; returns "" for a
    valid PDF that contains no extractable text.
    """
    parts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text)
    return "\n".join(parts).strip()
