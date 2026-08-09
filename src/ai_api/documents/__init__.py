"""Turn an invoice's attached document into invoice lines.

A stage of its own, not a step in the sync. The sync's job is to land the ledger
and advance a watermark; extraction is per-invoice, LLM-bound, and fails for
reasons that have nothing to do with the ERP. Inlining it would mean an LLM
outage stalls the ledger and a sync run's duration becomes a function of invoice
count.

    python -m ai_api.documents.runner                     # every pending invoice
    python -m ai_api.documents.runner --limit 20          # pace a backlog
    python -m ai_api.documents.runner --invoice-id <id>   # one invoice
"""
from .extractor import ExtractedLines, UnsupportedMediaError, extract_lines
from .reconcile import ReconcileResult, reconcile

__all__ = [
    "ExtractedLines",
    "ReconcileResult",
    "UnsupportedMediaError",
    "extract_lines",
    "reconcile",
]
