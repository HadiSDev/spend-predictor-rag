"""What the model already answered, so it is not asked twice."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, UniqueConstraint
from sqlmodel import Field, SQLModel

from web_api.db.models._base import _ts, _uuid


class CategorizationCache(SQLModel, table=True):
    """One remembered answer, keyed by the facts that produced it."""

    __tablename__ = "categorization_cache"
    __table_args__ = (
        UniqueConstraint(
            "question_key", "tree_hash", name="uq_categorization_cache_question"
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    question_key: str = Field(sa_type=String, nullable=False, index=True)
    tree_hash: str = Field(sa_type=String, nullable=False)
    spend_category_id: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    confidence: Optional[float] = Field(default=None)
    rationale: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    question_sample: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    created_at: datetime = Field(sa_column=_ts())
