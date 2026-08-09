"""Fixtures for web API tests: in-memory SQLite, seed data, fake Clerk verifier.

No live Clerk or Postgres required — the DB engine is monkeypatched to SQLite
and the token verifier is overridden via FastAPI ``dependency_overrides``.
"""
from __future__ import annotations

import base64
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from web_api.db.models import (
    Company,
    ErpAccount,
    ErpEntry,
    ErpIntegration,
    File,
    Invoice,
    InvoiceLine,
    Organization,
)
from web_api import deps
from web_api.app import create_app
from web_api.auth import ClerkPrincipal, TokenVerificationError
from web_api.clerk_client import get_clerk_client
from web_api.routers.webhooks import SvixWebhookVerifier, get_webhook_verifier

# A valid Svix signing secret for tests (base64 payload behind the whsec_ prefix).
TEST_WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"clerk-org-sync-test-secret-32b!!").decode()

# Tokens map to Clerk principals. Org ids match the seeded organizations so a
# provisioned user lands in the right tenant.
PRINCIPALS: dict[str, ClerkPrincipal] = {
    "tokA": ClerkPrincipal("userA", "clerk_orgA", "Org A", "org:admin", "a@a.com", "Alice"),
    "tokB": ClerkPrincipal("userB", "clerk_orgB", "Org B", "org:member", "b@b.com", "Bob"),
    "tok_weirdrole": ClerkPrincipal("userD", "clerk_orgA", "Org A", "org:billing", None, None),
    "tok_noorg": ClerkPrincipal("userC", None, None, None, None, None),
    "tok_empty": ClerkPrincipal("userE", "clerk_orgEmpty", "Empty Org", "org:admin", "e@e.com", "Eve"),
    # Additional Org A roles for the authorization matrix.
    "tok_moderatorA": ClerkPrincipal("userMod", "clerk_orgA", "Org A", "org:moderator", "mod@a.com", "Mod"),
    "tok_memberA": ClerkPrincipal("userMem", "clerk_orgA", "Org A", "org:member", "mem@a.com", "Mem"),
    "tok_viewerA": ClerkPrincipal("userVie", "clerk_orgA", "Org A", "org:viewer", "vie@a.com", "Vie"),
    # Platform system admin (low org role, but is_system_admin=True) in Org A.
    "tok_sysadmin": ClerkPrincipal("userSys", "clerk_orgA", "Org A", "org:member", "sys@a.com", "Sys", is_system_admin=True),
}


class FakeVerifier:
    def verify(self, token: str) -> ClerkPrincipal:
        if token in PRINCIPALS:
            return PRINCIPALS[token]
        raise TokenVerificationError(f"unknown test token {token!r}")


@pytest.fixture
def engine(monkeypatch):
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(deps, "engine", eng)
    return eng


@pytest.fixture
def seed(engine):
    """Two tenants: Org A (1 invoice, 2 lines) and Org B (1 invoice, 1 line)."""
    ids: dict[str, str] = {}
    with Session(engine) as s:
        org_a = Organization(name="Org A", clerk_org_id="clerk_orgA")
        org_b = Organization(name="Org B", clerk_org_id="clerk_orgB")
        s.add(org_a)
        s.add(org_b)
        s.commit()
        # Both report in DKK, which is what their seeded invoices are posted in.
        comp_a = Company(organization_id=org_a.id, name="Acme A", base_currency="DKK")
        comp_b = Company(organization_id=org_b.id, name="Beta B", base_currency="DKK")
        s.add(comp_a)
        s.add(comp_b)
        s.commit()
        # DKK invoices for DKK-reporting companies: converted at rate 1, the
        # ordinary case, so base-currency reads and reports have data to work on.
        inv_a = Invoice(company_id=comp_a.id, invoice_number="A1",
                        invoice_date=date(2025, 7, 1), currency="DKK",
                        total=Decimal("100.00"), status="uncategorized",
                        base_currency="DKK", base_total=Decimal("100.00"),
                        fx_rate=Decimal("1"), fx_rate_date=date(2025, 7, 1))
        inv_b = Invoice(company_id=comp_b.id, invoice_number="B1",
                        invoice_date=date(2025, 8, 1), currency="DKK",
                        total=Decimal("50.00"), status="uncategorized",
                        base_currency="DKK", base_total=Decimal("50.00"),
                        fx_rate=Decimal("1"), fx_rate_date=date(2025, 8, 1))
        s.add(inv_a)
        s.add(inv_b)
        s.commit()
        converted = {"base_currency": "DKK", "fx_rate": Decimal("1")}
        line_a1 = InvoiceLine(company_id=comp_a.id, invoice_id=inv_a.id, description="Cloud server",
                              amount=Decimal("80.00"), status="uncategorized", sequence=0,
                              base_amount=Decimal("80.00"),
                              fx_rate_date=date(2025, 7, 1), **converted)
        line_a2 = InvoiceLine(company_id=comp_a.id, invoice_id=inv_a.id, description="Support",
                              amount=Decimal("20.00"), status="ai_categorized", sequence=1,
                              level_2="Technology", account_code="6010",
                              account_name="Cloud Hosting & Infrastructure",
                              confidence=Decimal("0.900"), rationale="matched",
                              base_amount=Decimal("20.00"),
                              fx_rate_date=date(2025, 7, 1), **converted)
        line_b1 = InvoiceLine(company_id=comp_b.id, invoice_id=inv_b.id, description="Legal retainer",
                              amount=Decimal("50.00"), status="uncategorized", sequence=0,
                              base_amount=Decimal("50.00"),
                              fx_rate_date=date(2025, 8, 1), **converted)
        s.add(line_a1)
        s.add(line_a2)
        s.add(line_b1)
        s.commit()
        ids = {
            "org_a": org_a.id, "org_b": org_b.id,
            "comp_a": comp_a.id, "comp_b": comp_b.id,
            "inv_a": inv_a.id, "inv_b": inv_b.id,
            "line_a1": line_a1.id, "line_a2": line_a2.id, "line_b1": line_b1.id,
        }
    return ids


@pytest.fixture
def voucher_seed(engine, seed):
    """Extends ``seed`` with a connected ERP integration + a real voucher for Org A.

    General-purpose, for any test that needs an invoice traceable back to an
    ERP integration through its postings: a connected ``ErpIntegration``, one
    ``ErpAccount``, a ``File`` linked to ``seed['inv_a']``, and three postings
    on voucher ``"4821"`` — a purchase-invoice entry (linking the voucher to
    the invoice), a payment entry (excluded from entry listings, but still a
    real posting), and a lone posting with no voucher at all.
    """
    ids = dict(seed)
    with Session(engine) as s:
        integ = ErpIntegration(
            company_id=ids["comp_a"], erp_type="mock", label="Debug ERP",
            connected_at=datetime.now(timezone.utc),
        )
        s.add(integ)
        s.commit()

        account = ErpAccount(
            erp_integration_id=integ.id, erp_account_code="6200",
            erp_account_name="Software", erp_account_type="expense",
        )
        s.add(account)
        s.commit()

        file_row = File(
            company_id=ids["comp_a"], filename="invoice.pdf",
            file_type="invoice_pdf", storage_path="vouchers/4821/invoice.pdf",
        )
        s.add(file_row)
        s.commit()

        invoice = s.get(Invoice, ids["inv_a"])
        invoice.file_id = file_row.id
        s.add(invoice)
        s.commit()

        entry_invoice = ErpEntry(
            company_id=ids["comp_a"], erp_account_id=account.id,
            source_invoice_id=ids["inv_a"], voucher_id="4821",
            entry_type="purchase_invoice", accounting_date=date(2025, 7, 1),
            debit_amount=Decimal("100.00"), currency="DKK",
        )
        entry_payment = ErpEntry(
            company_id=ids["comp_a"], erp_account_id=account.id,
            voucher_id="4821", entry_type="payment",
            accounting_date=date(2025, 7, 5),
            credit_amount=Decimal("100.00"), currency="DKK",
        )
        entry_unvouchered = ErpEntry(
            company_id=ids["comp_a"], erp_account_id=account.id,
            voucher_id=None, entry_type="journal_entry",
            accounting_date=date(2025, 7, 6),
            debit_amount=Decimal("10.00"), currency="DKK",
        )
        s.add(entry_invoice)
        s.add(entry_payment)
        s.add(entry_unvouchered)
        s.commit()

        ids.update({
            "integration_a": integ.id,
            "account_a": account.id,
            "file_a": file_row.id,
            "voucher": "4821",
            "entry_invoice": entry_invoice.id,
            "entry_payment": entry_payment.id,
            "entry_unvouchered": entry_unvouchered.id,
        })
    return ids


class RecordingClerkClient:
    """Fake outbound Clerk client that records org deletions instead of calling Clerk."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    @property
    def enabled(self) -> bool:
        return True

    def delete_organization(self, clerk_org_id: str) -> bool:
        self.deleted.append(clerk_org_id)
        return True


@pytest.fixture
def clerk_recorder():
    return RecordingClerkClient()


@pytest.fixture
def client(seed, clerk_recorder):
    app = create_app()
    app.dependency_overrides[deps.get_verifier] = lambda: FakeVerifier()
    # Real Svix verification against the test secret; outbound recorded, not sent.
    app.dependency_overrides[get_webhook_verifier] = lambda: SvixWebhookVerifier(TEST_WEBHOOK_SECRET)
    app.dependency_overrides[get_clerk_client] = lambda: clerk_recorder
    return TestClient(app)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
