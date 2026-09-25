"""An integration's native chart of accounts."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ErpAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    erp_integration_id: str
    erp_account_code: str
    erp_account_name: str
    erp_account_type: str | None = None
    parent_code: str | None = None
    is_active: bool
    sync_enabled: bool
    with_vat: bool


class ErpAccountUpdate(BaseModel):
    sync_enabled: bool | None = None
    with_vat: bool | None = None
