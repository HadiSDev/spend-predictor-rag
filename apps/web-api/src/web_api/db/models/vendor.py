from datetime import datetime
from typing import Optional

from sqlalchemy import String
from sqlmodel import Field, SQLModel

from ._base import _ts, _uuid


class Vendor(SQLModel, table=True):
    """A supplier in the global supplier database."""

    __tablename__ = "vendors"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(sa_type=String, nullable=False)
    country_code: Optional[str] = Field(sa_type=String, nullable=True)
    vat_number: Optional[str] = Field(sa_type=String, nullable=True)
    description: Optional[str] = Field(sa_type=String, nullable=True)
    description_source: Optional[str] = Field(sa_type=String, nullable=True)
    created_at: datetime = Field(sa_column=_ts())
