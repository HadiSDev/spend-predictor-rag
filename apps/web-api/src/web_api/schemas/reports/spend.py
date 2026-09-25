"""Report rows aggregated over categorized spend."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class CategorySpendRow(BaseModel):
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    currency: str | None = None
    amount_total: Decimal
    count: int
    unconverted_count: int = 0


class VendorSpendRow(BaseModel):
    vendor_id: str
    vendor_name: str
    currency: str | None = None
    amount_total: Decimal
    count: int
    unconverted_count: int = 0
