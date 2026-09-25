from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class Organization(SQLModel, table=True):
    __tablename__ = "organizations"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(sa_type=String, nullable=False)
    slug: Optional[str] = Field(sa_type=String, nullable=True, unique=True, default=None)
    status: str = Field(sa_type=String, nullable=False, default="active")
    suspended_at: Optional[datetime] = Field(sa_type=DateTime(timezone=True), nullable=True, default=None)
    clerk_org_id: Optional[str] = Field(sa_type=String, nullable=True, unique=True, default=None)
    created_at: datetime = Field(sa_column=_ts())

    users: list["User"] = Relationship(back_populates="organization")
    companies: list["Company"] = Relationship(back_populates="organization")
    spend_trees: list["SpendTree"] = Relationship(back_populates="organization")
