"""Spend trees as listed and read, and what deleting a node cost."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..spend_trees.categories import SpendCategoryRead


class SpendTreeRead(BaseModel):
    """A tree in the list view, with what a manager needs to choose between them."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    max_depth: int
    source: str
    template_version: str | None = None
    archived_at: datetime | None = None
    created_at: datetime
    node_count: int = 0
    company_ids: list[str] = Field(default_factory=list)
    company_names: list[str] = Field(default_factory=list)


class SpendTreeDetailRead(SpendTreeRead):
    """One tree with every node, ordered so a client can build it in one pass."""

    nodes: list[SpendCategoryRead] = Field(default_factory=list)


class SpendTreeDeleteResult(BaseModel):
    """Deleting a node reports what it cost, in lines that now need review."""

    stale_lines: int = 0
