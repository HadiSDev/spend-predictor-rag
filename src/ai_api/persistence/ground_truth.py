"""AI-owned store for synthetic per-line ground truth.

The categorization *result* now lives directly on the domain ``InvoiceLine``.
What stays here is only the synthetic ground truth used for benchmarking the
categorizer against generated data — a concern that belongs to the AI project,
not the business domain. For real (non-synthetic) data there is no ground-truth
row; the AI treats ``verified`` lines as the reference truth instead.

Boundary: the row references the domain ``invoice_lines`` table by id only (FK
with cascade cleanup), with no ORM ``Relationship()`` back into the domain and
no back-population on any domain model. ``web_api`` never imports this module.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String
from sqlmodel import Field, SQLModel

# ai_api may import from web_api (one-way dependency). Reuse the shared id/ts
# helpers so timestamps behave identically to the domain tables.
from web_api.db.models._base import _ts, _uuid


class LineGroundTruth(SQLModel, table=True):
    """Synthetic ground truth for a single invoice line (benchmarking only)."""

    __tablename__ = "line_ground_truth"

    id: str = Field(default_factory=_uuid, primary_key=True)
    # References the domain line, by id only (no ORM relationship). Cascades so a
    # deleted line takes its ground-truth row with it.
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
