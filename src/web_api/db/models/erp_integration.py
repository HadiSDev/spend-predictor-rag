from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class ErpIntegration(SQLModel, table=True):
    __tablename__ = "erp_integrations"

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(sa_type=String, foreign_key="companies.id", nullable=False)
    erp_type: str = Field(sa_type=String, nullable=False)
    label: Optional[str] = Field(sa_type=String, nullable=True)
    connected_at: Optional[datetime] = Field(sa_type=DateTime(timezone=True), nullable=True)
    disconnected_at: Optional[datetime] = Field(sa_type=DateTime(timezone=True), nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    company: Optional["Company"] = Relationship(back_populates="erp_integrations")
    erp_accounts: list["ErpAccount"] = Relationship(back_populates="erp_integration")
    credential: Optional["ErpCredential"] = Relationship(
        back_populates="erp_integration",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "uselist": False},
    )
    erp_entries: list["ErpEntry"] = Relationship(back_populates="erp_integration")
    sync_states: list["SyncState"] = Relationship(back_populates="erp_integration")
