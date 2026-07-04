"""Abstract interface for all ERP integrations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from pydantic import BaseModel


# -- Data Transfer Objects (normalized connector output) ---------------------


class ErpAccountData(BaseModel):
    erp_account_code: str
    erp_account_name: str
    erp_account_type: str | None = None
    parent_code: str | None = None
    is_active: bool = True
    with_vat: bool = False  # whether the ERP account is configured with VAT
    raw: dict = {}


class ErpVendorData(BaseModel):
    erp_id: str
    name: str
    country_code: str | None = None
    vat_number: str | None = None
    description: str | None = None
    raw: dict = {}


class ErpInvoiceLineData(BaseModel):
    line_erp_id: str | None = None
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    amount: float
    native_account_code: str | None = None
    raw: dict = {}


class ErpInvoiceData(BaseModel):
    erp_id: str
    vendor_erp_id: str
    vendor_name: str
    invoice_number: str
    invoice_date: date
    currency: str
    total: float
    tax: float | None = None
    voucher_id: str | None = None
    # Attached scan document, if the voucher has one. The runner records these
    # as a File and links the Invoice to it via file_id.
    file_name: str | None = None
    file_ref: str | None = None  # storage key / download path
    lines: list[ErpInvoiceLineData] = []
    raw: dict = {}


class ErpEntryData(BaseModel):
    """A normalized GL posting (ledger entry) from an ERP.

    Entries are the atomic financial record. Each carries the ``voucher_id`` of
    the posting it belongs to; a single voucher may produce several entries (net,
    VAT, rounding, split accounts).
    """

    erp_entry_id: str
    voucher_id: str
    entry_type: str  # purchase_invoice | journal_entry | payment | credit_note
    erp_account_code: str
    accounting_date: date | None = None  # ledger posting date
    description: str | None = None
    debit_amount: float | None = None
    credit_amount: float | None = None
    currency: str | None = None
    raw: dict = {}


# -- Errors ------------------------------------------------------------------


class ErpConnectionError(Exception):
    """Network error, timeout, unreachable host."""


class ErpAuthError(Exception):
    """Invalid or expired credentials."""


class ErpRateLimitError(Exception):
    """Rate-limited by ERP. Retry after X seconds."""


class ErpDataError(Exception):
    """Malformed or unexpected data from ERP."""


# -- Abstract Connector ------------------------------------------------------


class ErpConnector(ABC):
    """Contract all ERP integrations must implement."""

    def __init__(self, config: dict) -> None:
        self.config = config

    @abstractmethod
    def authorize(self) -> str:
        """Handshake with the ERP and return a token/session string."""

    @abstractmethod
    def test_connection(self) -> bool:
        """Verify credentials and API reachability without fetching data."""

    @abstractmethod
    def fetch_accounts(self) -> list[ErpAccountData]:
        """Full chart of accounts from the ERP (native accounts)."""

    @abstractmethod
    def fetch_vendors(
        self, since: date | None = None
    ) -> list[ErpVendorData]:
        """Vendor master. Optional date filter for incremental sync."""

    @abstractmethod
    def fetch_invoices(
        self, since: date | None = None
    ) -> list[ErpInvoiceData]:
        """Purchase invoices with line items."""

    @abstractmethod
    def fetch_entries(
        self, since: date | None = None, account_codes: set[str] | None = None
    ) -> list[ErpEntryData]:
        """GL postings (entries). Each carries a ``voucher_id``.

        Entries are the primary ledger unit real ERPs expose. Optional ``since``
        filters incrementally by entry date. ``account_codes`` selects which
        native accounts to pull: ``None`` returns all accounts (unfiltered), an
        empty set returns no entries, and a non-empty set returns only entries
        whose account is in it.
        """

    @abstractmethod
    def fetch_invoice_scan(self, voucher_id: str) -> ErpInvoiceData | None:
        """The invoice scan attached to a voucher, or ``None`` if it has none.

        In the real ERP the scanned supplier invoice (lines + attached document)
        is a separate resource keyed by the voucher its entries carry. Vouchers
        that are not purchase invoices (payments, journal entries) return
        ``None``.
        """
