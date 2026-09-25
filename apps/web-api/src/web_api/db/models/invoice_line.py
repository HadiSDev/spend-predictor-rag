from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Date, Integer, Numeric, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid
from .enums import LineOrigin, LineStatus


class InvoiceLine(SQLModel, table=True):
    __tablename__ = "invoice_lines"

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(sa_type=String, foreign_key="companies.id", nullable=False)
    invoice_id: str = Field(sa_type=String, foreign_key="invoices.id", nullable=False)
    item_name: Optional[str] = Field(sa_type=String, nullable=True)
    description: Optional[str] = Field(sa_type=String, nullable=True)
    quantity: Optional[Decimal] = Field(sa_type=Numeric(12, 4), nullable=True)
    unit: Optional[str] = Field(sa_type=String, nullable=True)
    unit_price: Optional[Decimal] = Field(sa_type=Numeric(12, 4), nullable=True)
    amount: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)

    subtotal: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    tax_amount: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    tax_rate: Optional[Decimal] = Field(sa_type=Numeric(7, 3), nullable=True)
    discount: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)

    native_account_code: Optional[str] = Field(sa_type=String, nullable=True)

    origin: LineOrigin = Field(sa_type=String, nullable=False, default=LineOrigin.ERP)

    sequence: int = Field(sa_type=Integer, nullable=False, default=0)

    base_currency: Optional[str] = Field(sa_type=String(3), nullable=True)
    base_amount: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    fx_rate: Optional[Decimal] = Field(sa_type=Numeric(18, 8), nullable=True)
    fx_rate_date: Optional[date] = Field(sa_type=Date, nullable=True)

    status: LineStatus = Field(sa_type=String, nullable=False, default=LineStatus.UNCATEGORIZED)
    error_message: Optional[str] = Field(sa_type=String, nullable=True)

    verified_fields: list[str] = Field(
        sa_type=JSON, nullable=False, default_factory=list
    )

    level_1: Optional[str] = Field(sa_type=String, nullable=True)
    level_2: Optional[str] = Field(sa_type=String, nullable=True)
    level_3: Optional[str] = Field(sa_type=String, nullable=True)
    level_4: Optional[str] = Field(sa_type=String, nullable=True)
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
