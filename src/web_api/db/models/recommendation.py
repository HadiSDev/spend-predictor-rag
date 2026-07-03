from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Numeric, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class Recommendation(SQLModel, table=True):
    __tablename__ = "recommendations"

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(sa_type=String, foreign_key="companies.id", nullable=False)
    rec_type: str = Field(sa_type=String, nullable=False)
    category_level_2: Optional[str] = Field(sa_type=String, nullable=True)
    category_level_3: Optional[str] = Field(sa_type=String, nullable=True)
    current_vendor_id: Optional[str] = Field(sa_type=String, foreign_key="vendors.id", nullable=True)
    current_vendor_name: Optional[str] = Field(sa_type=String, nullable=True)
    annual_spend: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    alternative_name: Optional[str] = Field(sa_type=String, nullable=True)
    estimated_savings: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    savings_pct: Optional[Decimal] = Field(sa_type=Numeric(5, 2), nullable=True)
    confidence: Optional[Decimal] = Field(sa_type=Numeric(4, 3), nullable=True)
    source: Optional[str] = Field(sa_type=String, nullable=True)
    rationale: Optional[str] = Field(sa_type=String, nullable=True)
    dismissed: bool = Field(sa_type=Boolean, default=False)
    gt_savings: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    company: Optional["Company"] = Relationship(back_populates="recommendations")
