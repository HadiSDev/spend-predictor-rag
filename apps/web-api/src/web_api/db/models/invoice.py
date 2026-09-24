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
    # The supplier's invoice number as read from the attached document, beside
    # the as-posted `invoice_number` above — which extraction never rewrites,
    # exactly as `base_total` sits beside `total` rather than replacing it.
    #
    # Load-bearing because the as-posted value is frequently not an invoice
    # number at all: Billy's `suppliersInvoiceNo` is user-entered and often
    # null and `voucherNo` is blank at least as often, so the connector falls
    # back to the *bill id* — an internal identifier sitting in a field the
    # reader takes for the supplier's number. The number printed on the invoice
    # is the one a human reconciles against, and only the document has it.
    document_invoice_number: Optional[str] = Field(sa_type=String, nullable=True)
    invoice_date: Optional[date] = Field(sa_type=Date, nullable=True)
    currency: Optional[str] = Field(sa_type=String, nullable=True)
    total: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    tax: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)

    # What the *document* said about its own arithmetic, beside the as-posted
    # figures above — which extraction still never rewrites. The same rule
    # `document_invoice_number` follows, and for the same reason: when the two
    # disagree, the disagreement *is* the information, and overwriting either
    # destroys it.
    #
    # This is what makes reconciliation answerable. The rule used to ask whether
    # the document's lines summed to the *ERP's* total — two systems, two VAT
    # conventions, one comparison — and rejected correctly-read invoices for
    # arithmetic that was never wrong.
    #
    # Null means the document stated none, never a stated zero: a receipt often
    # prints no totals block at all, and folding the two together would make a
    # document nobody could read look like one that balances.
    #
    # `document_subtotal` is here for the read side. `InvoiceDetailRead` has to
    # reproduce the verdict the extraction stage reached, and without the net
    # figure it would report a gross-printed / net-posted invoice as disagreeing
    # where the stage said it agreed — the exact drift `web_api/reconcile.py`
    # exists in one place to prevent.
    document_total: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    document_tax: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)
    document_subtotal: Optional[Decimal] = Field(sa_type=Numeric(14, 2), nullable=True)

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

    # A human's correction of the supplier, for this invoice alone. Null is "no
    # correction — use the linked Vendor", and is the ordinary case.
    #
    # These exist because `Vendor` is a **global** catalog shared across
    # organizations: writing a correction through to the vendor row would rewrite
    # the supplier for every other tenant, silently, and no permission check on
    # the invoice endpoint could fix that. So the correction lands here, and
    # readers resolve `override ?? vendor.value`.
    #
    # Never written by a connector, a sync or an extraction — only by a human.
    supplier_name: Optional[str] = Field(sa_type=String, nullable=True)
    supplier_country_code: Optional[str] = Field(sa_type=String(2), nullable=True)
    supplier_vat_number: Optional[str] = Field(sa_type=String, nullable=True)

    # Which fields a human has settled, and who settled them when.
    #
    # Per field, not per row, and that is load-bearing: a row-level flag would
    # freeze the invoice against the ERP entirely, so a reviewer correcting a
    # typo'd invoice number would also stop a genuine later re-posting of the
    # total from ever reaching us. The list keeps the sync doing its job
    # everywhere a human has not spoken (see ai_api/sync/runner.py).
    #
    # Defaults to `[]`, never null: "nothing settled" is a fact, not an unknown.
    # `verified_by` holds the acting user's id and never `system` — an automated
    # write is not a verification.
    verified_fields: list[str] = Field(
        sa_type=JSON, nullable=False, default_factory=list
    )
    verified_at: Optional[datetime] = Field(
        sa_type=DateTime(timezone=True), nullable=True
    )
    verified_by: Optional[str] = Field(sa_type=String, nullable=True)

    status: InvoiceStatus = Field(sa_type=String, nullable=False, default=InvoiceStatus.UNCATEGORIZED)
    # Where the header came from: 'erp' (posted by the ERP) or 'pdf_extraction'
    # (our AI's parse of a document). Provenance, which tells a reviewer how much
    # to trust a value — it no longer decides whether the value may be corrected.
    # Every parsed field is correctable by a management role whatever this says;
    # what protects a correction is `verified_fields` above, not this column.
    source: str = Field(sa_type=String, nullable=False, default="erp")
    error_message: Optional[str] = Field(sa_type=String, nullable=True)

    # Document processing: whether the attached scan has been turned into lines.
    # Independent of `status` above, which is the categorization rollup — one
    # says whether we have read the document, the other whether the resulting
    # spend has been categorized. An invoice with no scan is `not_applicable`,
    # which is the ordinary case and not a failure.
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
    # The vendor is a global supplier row; it holds no back-reference to invoices.
    vendor: Optional["Vendor"] = Relationship()
    file: Optional["File"] = Relationship(back_populates="invoices")
    lines: list["InvoiceLine"] = Relationship(
        back_populates="invoice",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    entries: list["ErpEntry"] = Relationship(back_populates="source_invoice")
