"""Categories proposed for a tree, with their evidence."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SuggestionEvidenceRead(BaseModel):
    """One line that argued for a suggestion."""

    id: str
    item_name: str | None = None
    description: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    vendor_name: str | None = None
    invoice_id: str | None = None
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    confidence: Decimal | None = None


class SpendCategorySuggestionRead(BaseModel):
    """A category the tree is missing, with where it would go and why."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    spend_tree_id: str
    company_id: str | None = None
    parent_id: str | None = None
    parent_path: str | None = None
    name: str
    description: str | None = None
    rationale: str | None = None
    state: str
    created_category_id: str | None = None
    acceptable: bool = True
    evidence: list[SuggestionEvidenceRead] = []
    evidence_count: int = 0
    created_at: datetime | None = None


class SuggestionResolveResult(BaseModel):
    """What accepting or dismissing did."""

    id: str
    state: str
    created_category_id: str | None = None
