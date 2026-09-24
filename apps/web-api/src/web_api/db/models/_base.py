"""Shared helpers for model definitions."""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, DateTime, func
from sqlmodel import SQLModel


def _uuid() -> str:
    return str(uuid4())


def _ts() -> Column:
    return Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
