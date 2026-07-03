from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, JSON, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class ErpAccount(SQLModel, table=True):
    """A native chart-of-accounts node from an ERP system."""

    __tablename__ = "erp_accounts"

    id: str = Field(default_factory=_uuid, primary_key=True)
    erp_integration_id: str = Field(sa_type=String, foreign_key="erp_integrations.id", nullable=False)
    erp_account_code: str = Field(sa_type=String, nullable=False)
    erp_account_name: str = Field(sa_type=String, nullable=False)
    erp_account_type: Optional[str] = Field(sa_type=String, nullable=True)
    parent_code: Optional[str] = Field(sa_type=String, nullable=True)
    is_active: bool = Field(sa_type=Boolean, default=True)  # mirrors the ERP's active flag
    # Our sync selection: only enabled accounts are fetched for entries. Distinct
    # from is_active. Preserved across re-syncs (never reset from the ERP).
    sync_enabled: bool = Field(sa_type=Boolean, default=True)
    # Whether the ERP account is configured with VAT (metadata; used later in
    # categorization to decide inclusive/exclusive VAT summation).
    with_vat: bool = Field(sa_type=Boolean, default=False)
    raw_json: Optional[dict] = Field(sa_type=JSON, nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    erp_integration: Optional["ErpIntegration"] = Relationship(back_populates="erp_accounts")
