"""Shared status vocabularies as string enums.

These are ``str`` subclasses, so members compare equal to their raw string value
(``LineStatus.VERIFIED == "verified"``) and serialize as plain strings — the DB
columns stay ``String`` (no PG enum type, no migration churn) while call sites get
a typed, typo-proof vocabulary. ai_api reaches these through the one-way
``ai_api → web_api`` dependency.
"""
from __future__ import annotations

from enum import Enum


class LineStatus(str, Enum):
    """Per-line categorization lifecycle."""

    UNCATEGORIZED = "uncategorized"  # imported, not yet categorized
    AI_FAILED = "ai_failed"          # the AI could not categorize it
    AI_CATEGORIZED = "ai_categorized"  # the AI assigned a category
    VERIFIED = "verified"            # a human confirmed or corrected it


class InvoiceStatus(str, Enum):
    """Invoice status, rolled up from its lines."""

    UNCATEGORIZED = "uncategorized"  # no line categorized yet
    CATEGORIZED = "categorized"      # lines AI-categorized, not all verified
    VERIFIED = "verified"            # every line verified
