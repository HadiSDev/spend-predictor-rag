"""Requests that create or change a spend tree."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SpendTreeCreate(BaseModel):
    """Create a tree: empty, or cloned from an existing one."""

    name: str = Field(min_length=1)
    max_depth: int = Field(default=3, ge=3, le=4)
    source_tree_id: str | None = None


class SpendTreeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    max_depth: int | None = Field(default=None, ge=3, le=4)
