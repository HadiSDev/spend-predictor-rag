"""Test helpers shared across ai-api's suite: a scriptable connector and its data.

Kept out of ``conftest.py`` so a test can import them by name. ``tests/`` is not
a package — both apps have one, and two packages named ``tests`` collide in a
single pytest session — so ``from .conftest import …`` is not available. This
module's name is unique across the workspace instead, and pytest puts the
directory on ``sys.path`` (``pythonpath`` in the pytest config).
"""
from __future__ import annotations

from datetime import date

from web_api.connectors import register_connector
from web_api.connectors.base import (
    CredentialField,
    DocumentPayload,
    ErpAccountData,
    ErpConnector,
    ErpEntryData,
    ErpInvoiceData,
    ErpInvoiceLineData,
    ErpVendorData,
)


# -- A connector whose behaviour a test can script ---------------------------

ACCOUNTS = [
    ErpAccountData(erp_account_code="6010", erp_account_name="Cloud Hosting"),
    ErpAccountData(erp_account_code="2610", erp_account_name="Input VAT", with_vat=True),
]

VENDORS = [
    ErpVendorData(erp_id="V-1", name="Contoso ApS", country_code="DK", vat_number="DK99999999"),
]

ENTRIES = [
    ErpEntryData(erp_entry_id="E-1", voucher_id="V1", entry_type="purchase_invoice",
                 erp_account_code="6010", accounting_date=date(2026, 3, 2),
                 description="Cloud hosting March", debit_amount=800.0, currency="DKK"),
    ErpEntryData(erp_entry_id="E-2", voucher_id="V1", entry_type="purchase_invoice",
                 erp_account_code="2610", accounting_date=date(2026, 3, 2),
                 description="VAT 25%", debit_amount=200.0, currency="DKK"),
    ErpEntryData(erp_entry_id="E-3", voucher_id="PAY1", entry_type="payment",
                 erp_account_code="6010", accounting_date=date(2026, 3, 9),
                 description="Payment", credit_amount=1000.0, currency="DKK"),
]

INVOICE = ErpInvoiceData(
    erp_id="INV-1", vendor_erp_id="V-1", vendor_name="Contoso ApS",
    invoice_number="2026-001", invoice_date=date(2026, 3, 2), currency="DKK",
    total=1000.0, tax=200.0, voucher_id="V1", file_name="inv-1.pdf",
    lines=[
        ErpInvoiceLineData(line_erp_id="L-1", description="Cloud hosting", amount=800.0,
                           native_account_code="6010"),
    ],
)


#: Distinguishes "the test scripted None" from "the test scripted nothing" —
#: a scan being absent is itself a case worth scripting.
_UNSET = object()


class FakeConnector(ErpConnector):
    """A connector the tests drive. Class-level switches, reset per test.

    `config` is captured on construction so a test can assert which credentials
    actually reached the connector.

    `accounts` / `entries` / `scan` override the module constants above for one
    test. They default to `None` / `_UNSET`, so a test that scripts nothing gets
    exactly the data every existing test was pinned against.
    """

    display_label = "Fake ERP"
    credential_fields = [
        CredentialField(name="base_url", label="Base URL", default="http://fake"),
        CredentialField(name="api_key", label="API key", secret=True, default="fake-key"),
    ]

    # Scripting switches.
    reachable = True
    raise_on_fetch = False
    seen_configs: list[dict] = []
    seen_since: list[date | None] = []
    accounts: list[ErpAccountData] | None = None
    entries: list[ErpEntryData] | None = None
    scan: object = _UNSET

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        FakeConnector.seen_configs.append(self.config)

    @classmethod
    def reset(cls) -> None:
        cls.reachable = True
        cls.raise_on_fetch = False
        cls.seen_configs = []
        cls.seen_since = []
        cls.accounts = None
        cls.entries = None
        cls.scan = _UNSET

    @classmethod
    def _scan(cls) -> ErpInvoiceData | None:
        return INVOICE if cls.scan is _UNSET else cls.scan  # type: ignore[return-value]

    def authorize(self) -> None:
        return None

    def test_connection(self) -> bool:
        return FakeConnector.reachable

    def fetch_accounts(self) -> list[ErpAccountData]:
        return list(FakeConnector.accounts if FakeConnector.accounts is not None else ACCOUNTS)

    def fetch_vendors(self, since: date | None = None) -> list[ErpVendorData]:
        return list(VENDORS)

    def fetch_entries(self, since: date | None = None,
                      account_codes: set[str] | None = None) -> list[ErpEntryData]:
        FakeConnector.seen_since.append(since)
        if FakeConnector.raise_on_fetch:
            raise RuntimeError("fake ERP blew up mid-fetch")
        rows = list(FakeConnector.entries if FakeConnector.entries is not None else ENTRIES)
        if account_codes is not None:
            rows = [e for e in rows if e.erp_account_code in account_codes]
        return rows

    def fetch_invoices(self, since: date | None = None) -> list[ErpInvoiceData]:
        scan = FakeConnector._scan()
        return [scan] if scan is not None else []

    def fetch_invoice_scan(self, voucher_id: str) -> ErpInvoiceData | None:
        scan = FakeConnector._scan()
        if scan is None or voucher_id != scan.voucher_id:
            return None
        return scan

    def fetch_invoice_document(self, voucher_id: str) -> DocumentPayload | None:
        return None


register_connector("fake", FakeConnector)


# -- A typed chart and a fully-posted voucher (stand-in line tests) ----------

# A chart that actually declares account types — the module default leaves them
# null, which is what every pre-existing test is pinned against.
TYPED_ACCOUNTS = [
    ErpAccountData(erp_account_code="6010", erp_account_name="Cloud Hosting",
                   erp_account_type="expense"),
    ErpAccountData(erp_account_code="6020", erp_account_name="Software",
                   erp_account_type="expense"),
    ErpAccountData(erp_account_code="2610", erp_account_name="Input VAT",
                   erp_account_type="asset", with_vat=True),
    ErpAccountData(erp_account_code="8010", erp_account_name="Trade payables",
                   erp_account_type="liability"),
]


def entry(erp_id: str, account: str, debit: float | None = None,
           credit: float | None = None, description: str = "",
           voucher: str = "V1") -> ErpEntryData:
    return ErpEntryData(
        erp_entry_id=erp_id, voucher_id=voucher, entry_type="purchase_invoice",
        erp_account_code=account, accounting_date=date(2026, 3, 2),
        description=description, debit_amount=debit, credit_amount=credit,
        currency="DKK",
    )


# One voucher, fully posted: net expense, its VAT, and the payable that balances
# it. Only the first is spend.
BALANCED_VOUCHER = [
    entry("E-1", "6010", debit=800.0, description="Cloud hosting March"),
    entry("E-2", "2610", debit=200.0, description="VAT 25%"),
    entry("E-3", "8010", credit=1000.0, description="Contoso ApS"),
]

# The same voucher with its expense split across two accounts.
SPLIT_VOUCHER = [
    entry("E-1", "6010", debit=500.0, description="Cloud hosting March"),
    entry("E-2", "6020", debit=300.0, description="Licences"),
    entry("E-3", "2610", debit=200.0, description="VAT 25%"),
    entry("E-4", "8010", credit=1000.0, description="Contoso ApS"),
]

# A scan with no lines of its own — the case the stand-ins exist for.
SCAN_WITHOUT_LINES = ErpInvoiceData(
    erp_id="INV-1", vendor_erp_id="V-1", vendor_name="Contoso ApS",
    invoice_number="2026-001", invoice_date=date(2026, 3, 2), currency="DKK",
    total=1000.0, tax=200.0, voucher_id="V1", file_name="inv-1.pdf",
    lines=[],
)
