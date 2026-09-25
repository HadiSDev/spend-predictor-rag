"""Shared status vocabularies as string enums."""
from __future__ import annotations

from enum import Enum


class LineStatus(str, Enum):
    """Per-line categorization lifecycle."""

    UNCATEGORIZED = "uncategorized"
    AI_FAILED = "ai_failed"
    AI_CATEGORIZED = "ai_categorized"
    VERIFIED = "verified"


class InvoiceStatus(str, Enum):
    """Invoice status, rolled up from its lines."""

    UNCATEGORIZED = "uncategorized"
    CATEGORIZED = "categorized"
    VERIFIED = "verified"


EXPENSE_ACCOUNT_TYPE = "expense"


class LineOrigin(str, Enum):
    """Which source produced an invoice line."""

    ERP = "erp"
    DOCUMENT_AI = "document_ai"
    ENTRY_FALLBACK = "entry_fallback"
    HUMAN = "human"


class SpendTreeSource(str, Enum):
    """Where a spend tree came from."""

    DEFAULT_TEMPLATE = "default_template"
    CUSTOM = "custom"


class DocStatus(str, Enum):
    """Whether an invoice's attached document has been turned into lines."""

    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
