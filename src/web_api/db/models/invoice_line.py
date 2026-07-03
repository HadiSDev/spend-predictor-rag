from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Numeric, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid
from .enums import LineStatus


class InvoiceLine(SQLModel, table=True):
    __tablename__ = "invoice_lines"

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(sa_type=String, foreign_key="companies.id", nullable=False)
    invoice_id: str = Field(sa_type=String, foreign_key="invoices.id", nullable=False)
    description: Optional[str] = Field(sa_type=String, nullable=True)
    quantity: Optional[Decimal] = Field(sa_type=Numeric(12, 4), nullable=True)
    unit_price: Optional[Decimal] = Field(sa_type=Numeric(12, 4), nullable=True)
    amount: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    native_account_code: Optional[str] = Field(sa_type=String, nullable=True)

    status: LineStatus = Field(sa_type=String, nullable=False, default=LineStatus.UNCATEGORIZED)
    error_message: Optional[str] = Field(sa_type=String, nullable=True)

    level_1: Optional[str] = Field(sa_type=String, nullable=True)
    level_2: Optional[str] = Field(sa_type=String, nullable=True)
    level_3: Optional[str] = Field(sa_type=String, nullable=True)
    account_code: Optional[str] = Field(sa_type=String, nullable=True)
    account_name: Optional[str] = Field(sa_type=String, nullable=True)
    confidence: Optional[Decimal] = Field(sa_type=Numeric(4, 3), nullable=True)
    rationale: Optional[str] = Field(sa_type=String, nullable=True)

    spend_category_id: Optional[str] = Field(
        sa_type=String, foreign_key="spend_categories.id", nullable=True
    )

    raw_json: Optional[dict] = Field(sa_type=JSON, nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    company: Optional["Company"] = Relationship(sa_relationship_kwargs={"viewonly": True})
    invoice: Optional["Invoice"] = Relationship(back_populates="lines")
    spend_category: Optional["SpendCategory"] = Relationship()
