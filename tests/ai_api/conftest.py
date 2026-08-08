"""Fixtures for the sync runner: in-memory SQLite plus a scriptable connector.

Tenants here are built the way the customer API builds them — organization,
company, then a connected ``ErpIntegration`` — and never by the runner. That is
the whole point of the change under test: the runner reads its work, it does not
create it.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from ai_api.sync import runner
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
from web_api.db.models import Company, ErpCredential, ErpIntegration, Organization


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


class FakeConnector(ErpConnector):
    """A connector the tests drive. Class-level switches, reset per test.

    `config` is captured on construction so a test can assert which credentials
    actually reached the connector.
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

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        FakeConnector.seen_configs.append(self.config)

    @classmethod
    def reset(cls) -> None:
        cls.reachable = True
        cls.raise_on_fetch = False
        cls.seen_configs = []
        cls.seen_since = []

    def authorize(self) -> None:
        return None

    def test_connection(self) -> bool:
        return FakeConnector.reachable

    def fetch_accounts(self) -> list[ErpAccountData]:
        return list(ACCOUNTS)

    def fetch_vendors(self, since: date | None = None) -> list[ErpVendorData]:
        return list(VENDORS)

    def fetch_entries(self, since: date | None = None,
                      account_codes: set[str] | None = None) -> list[ErpEntryData]:
        FakeConnector.seen_since.append(since)
        if FakeConnector.raise_on_fetch:
            raise RuntimeError("fake ERP blew up mid-fetch")
        rows = list(ENTRIES)
        if account_codes is not None:
            rows = [e for e in rows if e.erp_account_code in account_codes]
        return rows

    def fetch_invoices(self, since: date | None = None) -> list[ErpInvoiceData]:
        return [INVOICE]

    def fetch_invoice_scan(self, voucher_id: str) -> ErpInvoiceData | None:
        return INVOICE if voucher_id == INVOICE.voucher_id else None

    def fetch_invoice_document(self, voucher_id: str) -> DocumentPayload | None:
        return None


register_connector("fake", FakeConnector)


@pytest.fixture(autouse=True)
def fake_connector():
    FakeConnector.reset()
    yield FakeConnector
    FakeConnector.reset()


@pytest.fixture
def engine(monkeypatch):
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(runner, "engine", eng)
    return eng


@pytest.fixture
def enc_key(monkeypatch):
    """A real Fernet key, so encrypt/decrypt round-trips like production."""
    from cryptography.fernet import Fernet
    from web_api import config as web_config

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(web_config, "WEB_API_CREDENTIAL_ENC_KEY", key)
    return key


@pytest.fixture
def make_tenant(engine):
    """Build a tenant the way the API does, never via the runner.

    Returns a callable so a test can build several and check that one run
    covers them all.
    """
    def _make(name: str = "Acme", *, erp_type: str = "fake",
              credentials: dict | None = None, connected: bool = True) -> dict:
        from web_api.credentials import encrypt_config

        with Session(engine) as s:
            org = Organization(name=f"{name} Org", clerk_org_id=f"clerk_{name}")
            s.add(org)
            s.commit()
            company = Company(organization_id=org.id, name=name)
            s.add(company)
            s.commit()
            integration = ErpIntegration(
                company_id=company.id,
                erp_type=erp_type,
                label=f"{name} connection",
                connected_at=None if not connected else _utcnow(),
                disconnected_at=None if connected else _utcnow(),
            )
            s.add(integration)
            s.commit()
            if credentials is not None:
                s.add(ErpCredential(erp_integration_id=integration.id,
                                    encrypted_config=encrypt_config(credentials)))
                s.commit()
            return {"org_id": org.id, "company_id": company.id,
                    "integration_id": integration.id, "name": name}

    return _make


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
