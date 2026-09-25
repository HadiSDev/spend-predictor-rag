"""Abstract interface for all ERP integrations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .credentials import CredentialField
from .documents import DocumentPayload
from .invoices import ErpInvoiceData, ErpVendorData
from .ledger import ErpAccountData, ErpEntryData


class ErpConnector(ABC):
    """Contract all ERP integrations must implement."""

    display_label: str = ""
    credential_fields: list[CredentialField] = []

    brand_slug: str | None = None
    description: str | None = None
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
        ...
    @abstractmethod
    def fetch_accounts(self) -> list[ErpAccountData]:
        """Full chart of accounts from the ERP (native accounts)."""

    @abstractmethod
    def fetch_vendors(
        self, since: date | None = None
    ) -> list[ErpVendorData]:
        """Vendor master."""

    @abstractmethod
    def fetch_invoices(
        self, since: date | None = None
    ) -> list[ErpInvoiceData]:
        """Purchase invoices with line items."""

    @abstractmethod
    def fetch_entries(
        self, since: date | None = None, account_codes: set[str] | None = None
    ) -> list[ErpEntryData]:
        """GL postings (entries)."""

    def voided_voucher_ids(self) -> set[str]:
        """Vouchers seen during the last fetch that the ERP has since voided."""
        return set()

    @abstractmethod
    def fetch_invoice_scan(self, voucher_id: str) -> ErpInvoiceData | None:
        """The invoice scan attached to a voucher, or ``None`` if it has none."""

    @abstractmethod
    def fetch_invoice_document(self, voucher_id: str) -> DocumentPayload | None:
        """The scanned document attached to a voucher, or ``None`` if it has none."""
