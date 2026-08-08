from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, JSON, Numeric, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class ErpEntry(SQLModel, table=True):
    """Raw financial entry from an ERP system (GL/journal entry)."""

    __tablename__ = "erp_entries"

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(sa_type=String, foreign_key="companies.id", nullable=False)
    # No direct erp_integration_id: the integration is reached through the entry's
    # account (erp_account_id → ErpAccount.erp_integration_id).
    erp_account_id: str = Field(sa_type=String, foreign_key="erp_accounts.id", nullable=False)
    source_invoice_id: Optional[str] = Field(sa_type=String, foreign_key="invoices.id", nullable=True)
    # The invoice line this posting came from, when the ERP says. **One line has
    # many entries** — an invoice line can be posted across several accounts —
    # so the link points this way, and a line's category is read through it.
    # Null for a posting that is not line-derived (input VAT, the payable, a
    # journal entry), which is also why the entry itself is never categorized:
    # the categorization belongs to the line.
    source_invoice_line_id: Optional[str] = Field(
        sa_type=String, foreign_key="invoice_lines.id", nullable=True
    )
    voucher_id: Optional[str] = Field(sa_type=String, nullable=True)
    entry_type: str = Field(sa_type=String, nullable=False)
    # The ledger posting/accounting date — the axis for period reporting.
    accounting_date: Optional[date] = Field(sa_type=Date, nullable=True)
    description: Optional[str] = Field(sa_type=String, nullable=True)
    debit_amount: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    credit_amount: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    currency: Optional[str] = Field(sa_type=String, nullable=True)
    erp_entry_id: Optional[str] = Field(sa_type=String, nullable=True)

    # Conversion into the company's base currency, at the rate in force on
    # `accounting_date`. Debit and credit are each converted from their own
    # posted value, never derived from one another. Null means "not converted".
    base_currency: Optional[str] = Field(sa_type=String(3), nullable=True)
    base_debit_amount: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    base_credit_amount: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    fx_rate: Optional[Decimal] = Field(sa_type=Numeric(18, 8), nullable=True)
    fx_rate_date: Optional[date] = Field(sa_type=Date, nullable=True)

    status: str = Field(sa_type=String, nullable=False, default="pending")
    error_message: Optional[str] = Field(sa_type=String, nullable=True)

    raw_json: Optional[dict] = Field(sa_type=JSON, nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    company: Optional["Company"] = Relationship(back_populates="erp_entries")
    erp_account: Optional["ErpAccount"] = Relationship(sa_relationship_kwargs={"viewonly": True})
    source_invoice: Optional["Invoice"] = Relationship(back_populates="entries")
