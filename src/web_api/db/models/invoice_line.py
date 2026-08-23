from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Date, Integer, Numeric, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid
from .enums import LineOrigin, LineStatus


class InvoiceLine(SQLModel, table=True):
    __tablename__ = "invoice_lines"

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(sa_type=String, foreign_key="companies.id", nullable=False)
    invoice_id: str = Field(sa_type=String, foreign_key="invoices.id", nullable=False)
    # What was bought, named. Short, expected on every line, and the value a
    # supplier comparison is actually about: "Figma Organization seat" is
    # comparable across suppliers in a way that a sentence of prose is not.
    #
    # Separate from `description` below because one field was doing both jobs.
    # Nullable despite being the always-present one: a stand-in line is built
    # from a ledger memo that is itself frequently null, and a NOT NULL column
    # would force the sync to invent a name.
    item_name: Optional[str] = Field(sa_type=String, nullable=True)
    # Supplementary prose the supplier printed, when it printed any. Frequently
    # absent, and nothing downstream may assume it is present. A source stating
    # only one text puts it in `item_name`, not here.
    description: Optional[str] = Field(sa_type=String, nullable=True)
    quantity: Optional[Decimal] = Field(sa_type=Numeric(12, 4), nullable=True)
    # The unit `quantity` is counted in ('pcs', 'hours', 'kg', 'months'). A bare
    # quantity is ambiguous — 12 against "Consulting" is twelve hours or twelve
    # days — and unit prices cannot be compared across suppliers without it.
    # Null is the ordinary case: an ERP bill line states an account and an
    # amount, not a unit of measure, and a posting has neither. Never inferred
    # from the description and never defaulted: "pcs" assumed over an hourly
    # line is a wrong figure presented with confidence.
    unit: Optional[str] = Field(sa_type=String, nullable=True)
    unit_price: Optional[Decimal] = Field(sa_type=Numeric(12, 4), nullable=True)
    amount: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    native_account_code: Optional[str] = Field(sa_type=String, nullable=True)

    # Which source produced this line. Stored rather than inferred: a stand-in
    # line and an extracted line can be identical in every other field, and the
    # difference decides whether the description can be trusted.
    origin: LineOrigin = Field(sa_type=String, nullable=False, default=LineOrigin.ERP)

    # Position on the invoice, as its source stated it. The line's `id` is a
    # random UUID, so ordering by it scrambles a document into an arbitrary
    # sequence — invisible while the Entries page listed postings, and wrong the
    # moment it lists lines: an invoice reads top to bottom.
    sequence: int = Field(sa_type=Integer, nullable=False, default=0)

    # Conversion into the company's base currency. A line has no date of its
    # own: it is converted at its invoice's `invoice_date`. `amount` stays as
    # posted; null base fields mean "not converted".
    base_currency: Optional[str] = Field(sa_type=String(3), nullable=True)
    base_amount: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    fx_rate: Optional[Decimal] = Field(sa_type=Numeric(18, 8), nullable=True)
    fx_rate_date: Optional[date] = Field(sa_type=Date, nullable=True)

    status: LineStatus = Field(sa_type=String, nullable=False, default=LineStatus.UNCATEGORIZED)
    error_message: Optional[str] = Field(sa_type=String, nullable=True)

    # Which of this line's fields a human has settled. Same rule and same reason
    # as `Invoice.verified_fields`: per field, so a sync still refreshes what
    # nobody has spoken for. Defaults to `[]`, never null.
    verified_fields: list[str] = Field(
        sa_type=JSON, nullable=False, default_factory=list
    )

    level_1: Optional[str] = Field(sa_type=String, nullable=True)
    level_2: Optional[str] = Field(sa_type=String, nullable=True)
    level_3: Optional[str] = Field(sa_type=String, nullable=True)
    # The fourth tier, set only when the company's tree is four levels deep —
    # the ordinary case leaves it null. Never inferred and never defaulted: a
    # level the taxonomy does not have is not a level.
    level_4: Optional[str] = Field(sa_type=String, nullable=True)
    account_code: Optional[str] = Field(sa_type=String, nullable=True)
    account_name: Optional[str] = Field(sa_type=String, nullable=True)
    confidence: Optional[Decimal] = Field(sa_type=Numeric(4, 3), nullable=True)
    rationale: Optional[str] = Field(sa_type=String, nullable=True)

    spend_category_id: Optional[str] = Field(
        sa_type=String, foreign_key="spend_categories.id", nullable=True
    )

    raw_json: Optional[dict] = Field(sa_type=JSON, nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    company: Optional["Company"] = Relationship(sa_relationship_kwargs={"viewonly": True})
    invoice: Optional["Invoice"] = Relationship(back_populates="lines")
    spend_category: Optional["SpendCategory"] = Relationship()
