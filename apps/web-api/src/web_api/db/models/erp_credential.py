from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class ErpCredential(SQLModel, table=True):
    """Encrypted connection config for an ErpIntegration.

    Kept separate from ``erp_integrations`` so secrets stay off the hot read path.
    ``encrypted_config`` is a Fernet token over the JSON config (base_url, api_key,
    …); it is only ever decrypted server-side to build a connector and is never
    serialized to API clients. One active credential per integration.
    """

    __tablename__ = "erp_credentials"

    id: str = Field(default_factory=_uuid, primary_key=True)
    erp_integration_id: str = Field(
        sa_type=String, foreign_key="erp_integrations.id", nullable=False, unique=True
    )
    encrypted_config: str = Field(sa_type=String, nullable=False)
    created_at: datetime = Field(sa_column=_ts())
    updated_at: Optional[datetime] = Field(
        sa_type=DateTime(timezone=True), nullable=True, default=None
    )

    erp_integration: Optional["ErpIntegration"] = Relationship(back_populates="credential")
