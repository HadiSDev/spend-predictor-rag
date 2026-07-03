from datetime import datetime
from typing import Optional

from sqlalchemy import String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class SpendCategory(SQLModel, table=True):
    """One node in a company's spend tree (its own target taxonomy).

    Distinct from ``ErpAccount`` (the ERP's native chart of accounts). The
    categorizer bridges ``ErpAccount`` → ``SpendCategory``.
    """

    __tablename__ = "spend_categories"

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(sa_type=String, foreign_key="companies.id", nullable=False)
    level_1: Optional[str] = Field(sa_type=String, nullable=True)  # "Direct" | "Indirect"
    level_2: str = Field(sa_type=String, nullable=False)
    level_3: Optional[str] = Field(sa_type=String, nullable=True)
    level_4: Optional[str] = Field(sa_type=String, nullable=True)
    description: Optional[str] = Field(sa_type=String, nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    company: Optional["Company"] = Relationship(back_populates="spend_categories")
