from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid
from .enums import SpendTreeSource


class SpendTree(SQLModel, table=True):
    """A named spend taxonomy, owned by an Organization."""

    __tablename__ = "spend_trees"

    id: str = Field(default_factory=_uuid, primary_key=True)
    organization_id: str = Field(
        sa_type=String, foreign_key="organizations.id", nullable=False
    )
    name: str = Field(sa_type=String, nullable=False)
    max_depth: int = Field(sa_type=Integer, nullable=False, default=3)
    source: SpendTreeSource = Field(
        sa_type=String, nullable=False, default=SpendTreeSource.CUSTOM
    )
    template_version: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    archived_at: Optional[datetime] = Field(
        sa_type=DateTime(timezone=True), nullable=True, default=None
    )
    created_at: datetime = Field(sa_column=_ts())

    organization: Optional["Organization"] = Relationship(back_populates="spend_trees")
    categories: list["SpendCategory"] = Relationship(back_populates="spend_tree")
    companies: list["Company"] = Relationship(back_populates="spend_tree")
