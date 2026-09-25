from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, Numeric, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from ._base import _ts, _uuid


class FxRate(SQLModel, table=True):
    """One daily reference rate: units of ``quote_currency`` per 1 EUR."""

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("quote_currency", "rate_date", name="uq_fx_rate_ccy_date"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    quote_currency: str = Field(sa_type=String(3), nullable=False, index=True)
    rate_date: date = Field(sa_type=Date, nullable=False, index=True)
    published_date: date = Field(sa_type=Date, nullable=False)
    rate: Decimal = Field(sa_type=Numeric(18, 8), nullable=False)
    source: Optional[str] = Field(sa_type=String, nullable=True)
    fetched_at: datetime = Field(sa_column=_ts())
