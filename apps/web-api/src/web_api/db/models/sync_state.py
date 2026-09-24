from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class SyncState(SQLModel, table=True):
    __tablename__ = "sync_state"

    id: str = Field(default_factory=_uuid, primary_key=True)
    erp_integration_id: str = Field(sa_type=String, foreign_key="erp_integrations.id", nullable=False)
    last_sync_at: Optional[datetime] = Field(sa_type=DateTime(timezone=True), nullable=True)
    last_invoice_date: Optional[date] = Field(sa_type=Date, nullable=True)
    status: Optional[str] = Field(sa_type=String, nullable=True)
    error_message: Optional[str] = Field(sa_type=String, nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    erp_integration: Optional["ErpIntegration"] = Relationship(back_populates="sync_states")
