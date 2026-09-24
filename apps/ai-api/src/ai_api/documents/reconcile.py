"""Does what the document said add up to what the ledger posted?

The rule itself lives in :mod:`web_api.reconcile`, because the *same* arithmetic
now answers a second question: whether a reviewer's hand-corrected lines still
sum to the invoice's total. Two copies would eventually disagree, and the
visible symptom would be an extraction accepted here that the invoice payload
then reports to a reviewer as not reconciling. `ai_api` imports `web_api` and
never the reverse, so the domain is the only place both callers can reach.

What differs is what each does with the verdict, and that stays here: an
extraction that does not reconcile is **rejected** outright — the stand-in lines
are a correct, if coarse, answer, and keeping them beats replacing them with a
confident wrong one — while a human's correction is only warned about.

This module remains the stage's import site so its call sites read in its own
vocabulary; it adds no arithmetic of its own.
"""
from __future__ import annotations

from web_api.reconcile import ReconcileResult, reconcile, tolerance_for

__all__ = ["ReconcileResult", "reconcile", "tolerance_for"]
