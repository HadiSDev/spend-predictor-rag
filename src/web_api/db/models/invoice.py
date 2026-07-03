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

    status: InvoiceStatus = Field(sa_type=String, nullable=False, default=InvoiceStatus.UNCATEGORIZED)
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
