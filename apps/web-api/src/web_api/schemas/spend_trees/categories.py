"""Spend-tree nodes as read, created and updated."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SpendCategoryRead(BaseModel):
    """One node."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    spend_tree_id: str
    parent_id: str | None = None
    depth: int
    name: str
    code: str | None = None
    sort_order: int
    description: str | None = None
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None


class SpendCategoryCreate(BaseModel):
    name: str = Field(min_length=1)
    parent_id: str | None = None
    code: str | None = None
    description: str | None = None
    sort_order: int | None = None


class SpendCategoryUpdate(BaseModel):
    """Partial update."""

    name: str | None = Field(default=None, min_length=1)
    parent_id: str | None = None
    code: str | None = None
    description: str | None = None
    sort_order: int | None = None
