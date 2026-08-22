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
    # What `quantity` counts, when the ERP says. Most do not — Billy's bill line
    # carries a quantity and no unit field at all — so None is the norm and is
    # never to be filled with a default.
    unit: str | None = None
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
    # The ERP's own id for the invoice line this posting came from, matching an
    # `ErpInvoiceLineData.line_erp_id` on the voucher's scan. One line may be
    # posted as several entries, so this is many-to-one. None for a posting with
    # no line behind it — input VAT, the payable, a journal entry — which is the
    # common case and not an error.
    source_line_erp_id: str | None = None
    accounting_date: date | None = None  # ledger posting date
    description: str | None = None
    debit_amount: float | None = None
    credit_amount: float | None = None
    currency: str | None = None
    raw: dict = {}


class DocumentPayload(BaseModel):
    """A fetched document's bytes and how to serve them."""

    content: bytes
    media_type: str = "application/pdf"
    filename: str


# -- Catalog metadata --------------------------------------------------------


class CredentialField(BaseModel):
    """One input a connector needs to authenticate.

    Describes the input, never a stored value: a ``secret`` field's value is
    write-only and is never returned by any endpoint.
    """

    name: str
    label: str
    required: bool = False
    secret: bool = False
    default: str | None = None


# -- Errors ------------------------------------------------------------------


class ErpConnectionError(Exception):
    """Network error, timeout, unreachable host."""


class ErpAuthError(Exception):
    """Invalid or expired credentials."""


class ErpRateLimitError(Exception):
    """Rate-limited by ERP. Retry after X seconds.

    ``retry_after`` is the delay the ERP asked for, in seconds, or ``None`` when
    it named none. It is what separates this from ``ErpDataError``: a caller can
    back off and come back, rather than treating the response as nonsense.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ErpDataError(Exception):
    """Malformed or unexpected data from ERP."""


# -- Abstract Connector ------------------------------------------------------


class ErpConnector(ABC):
    """Contract all ERP integrations must implement.

    ``display_label`` and ``credential_fields`` are what the connector catalog
    (``GET /api/v1/erp-types``) projects, so declaring them here is all a new
    connector needs to become selectable in a client.
    """

    #: Human-readable name for pickers. Defaults to the class name.
    display_label: str = ""
    #: The credentials this connector accepts, in the order to present them.
    credential_fields: list[CredentialField] = []

    # -- Brand metadata (all optional) --------------------------------------
    # A client must be able to present a connector recognisably without knowing
    # any connector by name, so a connector's identity is declared here and
    # nowhere else. Omitting all three yields exactly the catalog entry a
    # connector produced before these existed.

    #: Key for locating vendored artwork, e.g. ``"billy"`` → ``billy.svg``.
    brand_slug: str | None = None
    #: One line describing the ERP, for a picker card.
    description: str | None = None
    #: Where a user can read about the ERP or find their credentials.
    docs_url: str | None = None

    def __init__(self, config: dict) -> None:
        self.config = config

    @classmethod
    def label(cls) -> str:
        return cls.display_label or cls.__name__

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

    def voided_voucher_ids(self) -> set[str]:
        """Vouchers seen during the last fetch that the ERP has since voided.

        Not abstract: an ERP with no notion of voiding correctly reports none,
        and the default costs such a connector nothing.

        This exists because skipping a voided transaction is not enough. A
        transaction voided *after* we synced it is simply never mentioned again,
        so its postings stay in our ledger for good — counting spend that was
        undone, and (when the ERP re-books the same bill under a new voucher)
        putting one invoice under two vouchers with its lines rendered twice.

        Reporting the ids the fetch *observed* is deliberately narrow: it says
        "these are voided", never "everything else is still valid". A fetch is
        scoped by watermark and by account selection, so absence from it is not
        evidence of anything, and deleting on absence would delete the ledger.
        """
        return set()

    @abstractmethod
    def fetch_invoice_scan(self, voucher_id: str) -> ErpInvoiceData | None:
        """The invoice scan attached to a voucher, or ``None`` if it has none.

        In the real ERP the scanned supplier invoice (lines + attached document)
        is a separate resource keyed by the voucher its entries carry. Vouchers
        that are not purchase invoices (payments, journal entries) return
        ``None``.
        """

    @abstractmethod
    def fetch_invoice_document(self, voucher_id: str) -> DocumentPayload | None:
        """The scanned document attached to a voucher, or ``None`` if it has none.

        Keyed by voucher, exactly like ``fetch_invoice_scan`` — the document and
        the scan record are two views of one thing.

        ``None`` means "nothing is attached", which is the ordinary case for a
        payment or a journal entry. A fetch that *failed* must raise
        ``ErpConnectionError`` instead, so a caller can tell a missing document
        from an unreachable ERP.
        """
