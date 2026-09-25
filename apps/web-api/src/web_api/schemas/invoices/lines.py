"""Invoice lines as read and verified."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from ... import config


class InvoiceLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    invoice_id: str
    company_id: str
    item_name: str | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    native_account_code: str | None = None
    origin: str = "erp"
    sequence: int = 0
    currency: str | None = None
    base_currency: str | None = None
    base_amount: Decimal | None = None
    fx_rate: Decimal | None = None
    fx_rate_date: date | None = None
    status: str
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    account_code: str | None = None
    account_name: str | None = None
    confidence: Decimal | None = None
    rationale: str | None = None
    spend_category_id: str | None = None
    verified_fields: list[str] = []
    category_stale: bool = False
    needs_review: bool = False

    @model_validator(mode="after")
    def _derive_category_stale(self) -> "InvoiceLineRead":
        """A decision with no resolving node is stale."""
        decided = self.level_1 is not None or self.level_2 is not None
        object.__setattr__(
            self, "category_stale", decided and self.spend_category_id is None
        )
        object.__setattr__(
            self,
            "needs_review",
            self.status == "ai_categorized"
            and (
                self.confidence is None
                or float(self.confidence) < config.CATEGORIZATION_REVIEW_THRESHOLD
            ),
        )
        return self


class InvoiceLineVerify(BaseModel):
    """Verify a line, optionally correcting its category."""

    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    account_code: str | None = None
    account_name: str | None = None
    confidence: Decimal | None = None
    rationale: str | None = None
    spend_category_id: str | None = None
