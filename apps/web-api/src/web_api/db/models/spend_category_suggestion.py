from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, String
from sqlmodel import Field, SQLModel

from ._base import _ts, _uuid


class SuggestionState:
    """Where a suggestion stands."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class SpendCategorySuggestion(SQLModel, table=True):
    """A category a company's tree is missing, proposed with its evidence."""

    __tablename__ = "spend_category_suggestions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    spend_tree_id: str = Field(
        sa_type=String, foreign_key="spend_trees.id", nullable=False
    )
    company_id: Optional[str] = Field(
        sa_type=String, foreign_key="companies.id", nullable=True, default=None
    )
    parent_id: Optional[str] = Field(
        sa_type=String, foreign_key="spend_categories.id", nullable=True, default=None
    )
    name: str = Field(sa_type=String, nullable=False)
    description: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    rationale: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    evidence_line_ids: list = Field(default_factory=list, sa_column=Column(JSON))
    state: str = Field(sa_type=String, nullable=False, default=SuggestionState.PENDING)
    created_category_id: Optional[str] = Field(
        sa_type=String, foreign_key="spend_categories.id", nullable=True, default=None
    )
    resolved_by: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    resolved_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(sa_column=_ts())
