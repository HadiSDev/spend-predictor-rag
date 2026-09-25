"""Categorizer output and its hierarchy-enriched final form."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AccountChoice(BaseModel):
    """Categorizer output: the chosen leaf account + the buyer-derived L1."""

    account_code: str = Field(
        description="Chosen leaf account code, copied exactly from the candidate list."
    )
    account_name: str = Field(
        description="Chosen leaf account name, matching account_code."
    )
    level_1: Literal["Direct", "Indirect"] = Field(
        description="Spend class derived from the buyer's business: 'Direct' (cost of "
        "revenue) or 'Indirect' (overhead)."
    )
    confidence: float = Field(
        description="Confidence in the categorization, from 0.0 to 1.0."
    )
    rationale: str = Field(
        description="Brief justification for the account and Direct/Indirect choice."
    )


class CategorizedInvoice(BaseModel):
    """Final, hierarchy-enriched categorization (L2/L3/leaf from the chart)."""

    account_code: str = Field(description="Leaf account code from the chart of accounts.")
    account_name: str = Field(description="Leaf account name from the chart of accounts.")
    level_1: str = Field(description="Direct or Indirect, from the model (buyer-derived).")
    level_2: str = Field(description="Level-2 category from the chart of accounts.")
    level_3: str = Field(description="Level-3 subcategory from the chart of accounts.")
    confidence: float = Field(
        description="Confidence in the categorization, from 0.0 to 1.0."
    )
    rationale: str = Field(description="Brief justification for the categorization.")
