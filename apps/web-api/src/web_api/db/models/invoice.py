from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Integer, JSON, Numeric, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid
from .enums import DocStatus, InvoiceStatus


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(sa_type=String, foreign_key="companies.id", nullable=False)
    vendor_id: Optional[str] = Field(sa_type=String, foreign_key="vendors.id", nullable=True)
    file_id: Optional[str] = Field(sa_type=String, foreign_key="files.id", nullable=True)
    invoice_number: Optional[str] = Field(sa_type=String, nullable=True)
    document_invoice_number: Optional[str] = Field(sa_type=String, nullable=True)
    invoice_date: Optional[date] = Field(sa_type=Date, nullable=True)
    currency: Optional[str] = Field(sa_type=String, nullable=True)
    total: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    tax: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)

    document_total: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    document_tax: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    document_subtotal: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)

    base_currency: Optional[str] = Field(sa_type=String(3), nullable=True)
    base_total: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    base_tax: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    fx_rate: Optional[Decimal] = Field(sa_type=Numeric(18, 8), nullable=True)
    fx_rate_date: Optional[date] = Field(sa_type=Date, nullable=True)

    supplier_name: Optional[str] = Field(sa_type=String, nullable=True)
    supplier_country_code: Optional[str] = Field(sa_type=String(2), nullable=True)
    supplier_vat_number: Optional[str] = Field(sa_type=String, nullable=True)

    verified_fields: list[str] = Field(
        sa_type=JSON, nullable=False, default_factory=list
    )
    verified_at: Optional[datetime] = Field(
        sa_type=DateTime(timezone=True), nullable=True
    )
    verified_by: Optional[str] = Field(sa_type=String, nullable=True)

    status: InvoiceStatus = Field(sa_type=String, nullable=False, default=InvoiceStatus.UNCATEGORIZED)
    source: str = Field(sa_type=String, nullable=False, default="erp")
    error_message: Optional[str] = Field(sa_type=String, nullable=True)

    doc_status: DocStatus = Field(
        sa_type=String, nullable=False, default=DocStatus.NOT_APPLICABLE
    )
    doc_attempts: int = Field(sa_type=Integer, nullable=False, default=0)
    doc_error: Optional[str] = Field(sa_type=String, nullable=True)
    doc_processed_at: Optional[datetime] = Field(
        sa_type=DateTime(timezone=True), nullable=True
    )

    raw_json: Optional[dict] = Field(sa_type=JSON, nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    company: Optional["Company"] = Relationship(back_populates="invoices")
    vendor: Optional["Vendor"] = Relationship()
    file: Optional["File"] = Relationship(back_populates="invoices")
    lines: list["InvoiceLine"] = Relationship(
        back_populates="invoice",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    entries: list["ErpEntry"] = Relationship(back_populates="source_invoice")
