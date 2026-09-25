from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class SpendCategory(SQLModel, table=True):
    """One node in a spend tree (an organization's own target taxonomy)."""

    __tablename__ = "spend_categories"
    __table_args__ = (
        UniqueConstraint("spend_tree_id", "parent_id", "name", name="uq_spend_category_sibling"),
        UniqueConstraint("spend_tree_id", "code", name="uq_spend_category_code"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    spend_tree_id: str = Field(
        sa_type=String, foreign_key="spend_trees.id", nullable=False
    )
    parent_id: Optional[str] = Field(
        sa_type=String, foreign_key="spend_categories.id", nullable=True, default=None
    )
    depth: int = Field(sa_type=Integer, nullable=False, default=1)
    name: str = Field(sa_type=String, nullable=False)
    code: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    sort_order: int = Field(sa_type=Integer, nullable=False, default=0)

    level_1: Optional[str] = Field(sa_type=String, nullable=True)
    level_2: Optional[str] = Field(sa_type=String, nullable=True)
    level_3: Optional[str] = Field(sa_type=String, nullable=True)
    level_4: Optional[str] = Field(sa_type=String, nullable=True)

    description: Optional[str] = Field(sa_type=String, nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    spend_tree: Optional["SpendTree"] = Relationship(back_populates="categories")
    parent: Optional["SpendCategory"] = Relationship(
        sa_relationship_kwargs={"remote_side": "SpendCategory.id"}
    )
