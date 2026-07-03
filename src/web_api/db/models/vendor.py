from datetime import datetime
from typing import Optional

from sqlalchemy import String
from sqlmodel import Field, SQLModel

from ._base import _ts, _uuid


class Vendor(SQLModel, table=True):
    """A supplier in the global supplier database.

    Vendors are a shared catalog built from ERP master data and parsed invoices,
    not owned by any company or organization. Identity is the VAT number when
    present, otherwise the normalized name (see the sync runner). Invoices point
    at a vendor (``Invoice.vendor_id``); the vendor holds no back-reference to
    invoices or lines, and invoice lines do not reference a vendor at all.
    """

    __tablename__ = "vendors"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(sa_type=String, nullable=False)
    country_code: Optional[str] = Field(sa_type=String, nullable=True)
    vat_number: Optional[str] = Field(sa_type=String, nullable=True)
    description: Optional[str] = Field(sa_type=String, nullable=True)
    created_at: datetime = Field(sa_column=_ts())
