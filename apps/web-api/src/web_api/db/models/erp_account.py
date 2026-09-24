from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, JSON, String, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class ErpAccount(SQLModel, table=True):
    """A native chart-of-accounts node from an ERP system."""

    __tablename__ = "erp_accounts"
    # An account *is* `(integration, code)`. Two writers create these rows — the
    # sync runner and `POST /erp-integrations/{id}/refresh-accounts` — and when
    # they disagreed about identity the chart was silently stored twice, with the
    # copies drifting as each writer updated only its own. Both now match on this
    # key; the constraint is what stops a third writer from repeating it.
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
