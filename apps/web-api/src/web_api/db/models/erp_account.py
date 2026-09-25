from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, JSON, String, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class ErpAccount(SQLModel, table=True):
    """A native chart-of-accounts node from an ERP system."""

    __tablename__ = "erp_accounts"
    __table_args__ = (
        UniqueConstraint(
            "erp_integration_id", "erp_account_code", name="uq_erp_accounts_integration_code"
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    erp_integration_id: str = Field(sa_type=String, foreign_key="erp_integrations.id", nullable=False)
    erp_account_code: str = Field(sa_type=String, nullable=False)
    erp_account_name: str = Field(sa_type=String, nullable=False)
    erp_account_type: Optional[str] = Field(sa_type=String, nullable=True)
    parent_code: Optional[str] = Field(sa_type=String, nullable=True)
    is_active: bool = Field(sa_type=Boolean, default=True)
    sync_enabled: bool = Field(sa_type=Boolean, default=True)
    with_vat: bool = Field(sa_type=Boolean, default=False)
    raw_json: Optional[dict] = Field(sa_type=JSON, nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    erp_integration: Optional["ErpIntegration"] = Relationship(back_populates="erp_accounts")
