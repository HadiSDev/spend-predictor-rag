from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, String
from sqlmodel import Field, SQLModel

from ._base import _ts, _uuid


class WebhookEvent(SQLModel, table=True):
    """Idempotency + audit record for an inbound provider webhook."""

    __tablename__ = "webhook_events"

    id: str = Field(default_factory=_uuid, primary_key=True)
    provider: str = Field(sa_type=String, nullable=False)
    event_id: str = Field(sa_type=String, nullable=False, unique=True)
    event_type: Optional[str] = Field(sa_type=String, nullable=True)
    payload: Optional[dict] = Field(sa_type=JSON, nullable=True)
    processed: bool = Field(sa_type=Boolean, nullable=False, default=False)
    error: Optional[str] = Field(sa_type=String, nullable=True)
    received_at: datetime = Field(sa_column=_ts())
