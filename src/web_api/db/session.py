"""Database engine and session helpers for SQLModel."""
from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlmodel import Session, SQLModel, create_engine

from web_api.config import DATABASE_URL


def get_engine() -> Any:
    url = DATABASE_URL or "postgresql://spend_predictor:spend_predictor@localhost:5432/spend_predictor"
    return create_engine(url, echo=False)


engine = get_engine()


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
