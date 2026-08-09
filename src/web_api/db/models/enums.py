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


#: The ``ErpAccount.erp_account_type`` that means "this is money spent".
#: Everything else in a voucher is the counterparty (payables, bank) or
#: reclaimable VAT.
#:
#: Two things read this and they **must** agree: the voucher's Total Spend
#: (``_net_spend`` in ``web_api/routers/erp_entries.py``) and the sync runner's
#: stand-in lines. If one counted a posting the other did not, an invoice's lines
#: would not add up to the figure shown above them.
EXPENSE_ACCOUNT_TYPE = "expense"


class LineOrigin(str, Enum):
    """Which source produced an invoice line.

    Precedence is ``DOCUMENT_AI > ERP > ENTRY_FALLBACK``: the document is the only
    source that knows what was actually bought, the ERP's own bill lines are its
    statement of the same voucher, and a posting is the last resort. An invoice
    holds lines of exactly one origin at a time — two origins describe the same
    spend twice and its total would be double-counted.

    Stored, never inferred: a stand-in line and an extracted line can carry
    identical descriptions and amounts, and the difference — whether anyone has
    read the document — is not recoverable from the values.
    """

    ERP = "erp"                        # the ERP supplied the line itself
    DOCUMENT_AI = "document_ai"        # extracted from the attached document
    ENTRY_FALLBACK = "entry_fallback"  # stands in for one expense posting


class DocStatus(str, Enum):
    """Whether an invoice's attached document has been turned into lines.

    Distinct from ``InvoiceStatus``, which is the categorization rollup of the
    invoice's lines. One says whether we have read the document; the other says
    whether the resulting spend has been categorized and verified.
    """

    NOT_APPLICABLE = "not_applicable"  # no document attached — not a failure
    PENDING = "pending"                # has a document, awaiting extraction
    PROCESSING = "processing"          # claimed by a stage run
    PROCESSED = "processed"            # extraction succeeded
    FAILED = "failed"                  # extraction failed or did not reconcile
