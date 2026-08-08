from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, JSON, Numeric, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid
from .enums import InvoiceStatus


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(sa_type=String, foreign_key="companies.id", nullable=False)
    vendor_id: Optional[str] = Field(sa_type=String, foreign_key="vendors.id", nullable=True)
    file_id: Optional[str] = Field(sa_type=String, foreign_key="files.id", nullable=True)
    invoice_number: Optional[str] = Field(sa_type=String, nullable=True)
    invoice_date: Optional[date] = Field(sa_type=Date, nullable=True)
    currency: Optional[str] = Field(sa_type=String, nullable=True)
    total: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    tax: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)

    # Conversion into the company's base currency, at the rate in force on
    # `invoice_date`. `currency`/`total`/`tax` above stay exactly as posted —
    # they are the evidence these are derived from. Null base fields mean "not
    # converted", never "converted to zero".
    base_currency: Optional[str] = Field(sa_type=String(3), nullable=True)
    base_total: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    base_tax: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    # Units of base currency per 1 unit of `currency`: base = amount * fx_rate.
    fx_rate: Optional[Decimal] = Field(sa_type=Numeric(18, 8), nullable=True)
    # The publication date the rate was taken from — not necessarily
    # `invoice_date`, since a weekend resolves back to the prior business day.
    fx_rate_date: Optional[date] = Field(sa_type=Date, nullable=True)

    status: InvoiceStatus = Field(sa_type=String, nullable=False, default=InvoiceStatus.UNCATEGORIZED)
    # Provenance, which decides what may be corrected. 'erp' rows are as-posted
    # evidence and their header is read-only; 'pdf_extraction' rows came from the
    # AI's parse of a document and may be corrected by a human.
    source: str = Field(sa_type=String, nullable=False, default="erp")
    error_message: Optional[str] = Field(sa_type=String, nullable=True)

    raw_json: Optional[dict] = Field(sa_type=JSON, nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    company: Optional["Company"] = Relationship(back_populates="invoices")
    # The vendor is a global supplier row; it holds no back-reference to invoices.
    vendor: Optional["Vendor"] = Relationship()
    file: Optional["File"] = Relationship(back_populates="invoices")
    lines: list["InvoiceLine"] = Relationship(
        back_populates="invoice",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    entries: list["ErpEntry"] = Relationship(back_populates="source_invoice")
