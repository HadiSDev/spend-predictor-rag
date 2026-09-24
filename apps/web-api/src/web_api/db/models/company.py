from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: str = Field(default_factory=_uuid, primary_key=True)
    organization_id: str = Field(sa_type=String, foreign_key="organizations.id", nullable=False)
    name: str = Field(sa_type=String, nullable=False)
    country_code: Optional[str] = Field(sa_type=String, nullable=True)
    vat_number: Optional[str] = Field(sa_type=String, nullable=True)
    # The single currency this company's figures are presented in (ISO 4217).
    # A customer setting, like ErpAccount.sync_enabled: no connector, sync, or
    # account refresh may overwrite it.
    base_currency: str = Field(sa_type=String(3), nullable=False, default="EUR")
    # The spend taxonomy this company categorizes against. The tree is owned by
    # the organization, not by the company, so several companies may share one.
    # Nullable only so the column can be added to existing rows: a company
    # created through the API is always assigned one, falling back to the
    # organization's copy of the default template.
    spend_tree_id: Optional[str] = Field(
        sa_type=String, foreign_key="spend_trees.id", nullable=True, default=None
    )
    # Soft-deactivation: companies own financial data, so retiring one keeps it.
    # A platform system admin may still destroy a company outright — see
    # `web_api/company_deletion.py` — but that is for a company that should not
    # exist, and `is_active` never represents it: a deleted company is absent,
    # not present-and-false. A flag meaning "retired" in one place and
    # "destroyed" in another would make every listing depend on which wrote it.
    is_active: bool = Field(sa_type=Boolean, nullable=False, default=True)
    deactivated_at: Optional[datetime] = Field(sa_type=DateTime(timezone=True), nullable=True, default=None)
    created_at: datetime = Field(sa_column=_ts())

    organization: Optional["Organization"] = Relationship(back_populates="companies")
    spend_tree: Optional["SpendTree"] = Relationship(back_populates="companies")
    files: list["File"] = Relationship(back_populates="company")
    erp_integrations: list["ErpIntegration"] = Relationship(back_populates="company")
    invoices: list["Invoice"] = Relationship(back_populates="company")
    erp_entries: list["ErpEntry"] = Relationship(back_populates="company")
    recommendations: list["Recommendation"] = Relationship(back_populates="company")
