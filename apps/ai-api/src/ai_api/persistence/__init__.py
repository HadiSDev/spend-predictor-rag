"""ai_api-owned persistence.

The AI pipeline stores its own working data — synthetic ground truth for
benchmarking, and the categorizer's answer cache — here, separate from the
``web_api`` domain models. The
categorization *result* itself lives on the domain ``InvoiceLine``; only the
benchmarking ground truth stays in this store. These tables reference domain
rows by id only — no ORM relationship reaches back into the domain — preserving
the one-way ``ai_api → web_api`` dependency.
"""
from __future__ import annotations

from .categorization_cache import CategorizationCache
from .ground_truth import LineGroundTruth

__all__ = ["CategorizationCache", "LineGroundTruth"]
