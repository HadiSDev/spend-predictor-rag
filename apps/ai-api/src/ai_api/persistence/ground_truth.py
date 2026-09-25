"""AI-owned store for synthetic per-line ground truth."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String
from sqlmodel import Field, SQLModel

from web_api.db.models._base import _ts, _uuid


class LineGroundTruth(SQLModel, table=True):
    """Synthetic ground truth for a single invoice line (benchmarking only)."""

    __tablename__ = "line_ground_truth"

    id: str = Field(default_factory=_uuid, primary_key=True)
    invoice_line_id: str = Field(
        sa_type=String,
        foreign_key="invoice_lines.id",
        nullable=False,
        unique=True,
        ondelete="CASCADE",
    )

    gt_level_1: Optional[str] = Field(sa_type=String, nullable=True)
    gt_level_2: Optional[str] = Field(sa_type=String, nullable=True)
    gt_level_3: Optional[str] = Field(sa_type=String, nullable=True)
    gt_account_code: Optional[str] = Field(sa_type=String, nullable=True)

    created_at: datetime = Field(sa_column=_ts())
