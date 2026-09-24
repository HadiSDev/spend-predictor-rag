from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, Numeric, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from ._base import _ts, _uuid


class FxRate(SQLModel, table=True):
    """One daily reference rate: units of ``quote_currency`` per 1 EUR.

    Reference data, not tenant data — it carries no organization or company, and
    one row serves every company. Rates are cached against EUR (the base the ECB
    publishes against) rather than pairwise: any pair is derived as
    ``rate(EUR→B) / rate(EUR→A)``, so n currencies need n rows per date instead
    of n².
    """

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("quote_currency", "rate_date", name="uq_fx_rate_ccy_date"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    quote_currency: str = Field(sa_type=String(3), nullable=False, index=True)
    # The date this rate is looked up by. A non-publication date (weekend,
    # holiday) is cached here too, holding the prior publication's rate, so the
    # same Saturday is never re-requested.
    rate_date: date = Field(sa_type=Date, nullable=False, index=True)
    # The publication this rate actually comes from — equal to `rate_date` on a
    # business day, earlier on a weekend or holiday. Kept so a row cached under
    # a non-publication date can still report the true rate date, instead of a
    # lookup date dressed up as one.
    published_date: date = Field(sa_type=Date, nullable=False)
    rate: Decimal = Field(sa_type=Numeric(18, 8), nullable=False)
    source: Optional[str] = Field(sa_type=String, nullable=True)
    fetched_at: datetime = Field(sa_column=_ts())
