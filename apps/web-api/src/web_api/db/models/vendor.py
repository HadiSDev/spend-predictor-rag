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
    #: Who wrote ``description`` — ``web`` (researched) or ``human`` (corrected).
    #: Null means nobody has: the ordinary state, and the one enrichment fills.
    #:
    #: It exists because the catalog is **global**. An enrichment run that
    #: overwrote a description would rewrite a supplier for every tenant at once,
    #: including one a person had already corrected, and there would be no record
    #: that it had ever been corrected. The per-field ``verified_fields`` machinery
    #: does the same job on invoices and lines, but it is scoped to a tenant's own
    #: rows and would be a strange thing to grow onto a shared catalog.
    description_source: Optional[str] = Field(sa_type=String, nullable=True)
    created_at: datetime = Field(sa_column=_ts())
