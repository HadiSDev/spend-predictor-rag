from datetime import date, datetime, timezone
from decimal import Decimal

from sqlmodel import Session

from web_api.db.models import ErpAccount, ErpEntry, ErpIntegration, File, Invoice

from web_api_testkit import auth


def test_document_404s_when_no_file_is_attached(client, seed):
    # The seeded invoices have no File row, so there is nothing to serve.
    res = client.get(f"/api/v1/invoices/{seed['inv_a']}/document", headers=auth("tokA"))
    assert res.status_code == 404


def test_document_is_tenant_scoped(client, seed):
    # Org B's invoice must be indistinguishable from one that does not exist.
    res = client.get(f"/api/v1/invoices/{seed['inv_b']}/document", headers=auth("tokA"))
    assert res.status_code == 404


def test_invoice_read_reports_whether_a_document_exists(client, seed):
    body = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA")).json()
    assert body["has_document"] is False
    assert body["file_id"] is None


def test_document_502s_when_the_erp_is_unreachable(client, voucher_seed, monkeypatch):
    """A dead ERP must be reported as such, never as a missing document — the UI
    offers retry for one and a different message for the other."""
    from web_api import integrations
    from web_api.connectors.base import ErpConnectionError

    class DeadConnector:
        def fetch_invoice_document(self, voucher_id):
            raise ErpConnectionError("connection refused: internal-erp-host.local:5432")

    monkeypatch.setattr(integrations, "connector_for_integration", lambda *a: DeadConnector())

    res = client.get(
        f"/api/v1/invoices/{voucher_seed['inv_a']}/document", headers=auth("tokA")
    )
    assert res.status_code == 502
    # The ERP's raw error text must never reach the client — it stays server-side.
    assert "internal-erp-host" not in res.text


def test_document_404s_when_the_erp_has_no_document_for_the_voucher(
    client, voucher_seed, monkeypatch
):
    """The other half of the 404-vs-502 distinction: `None` means "nothing
    attached", not "unreachable", and must be reported as a 404 like any other
    missing document — never surfaced as a 502."""
    from web_api import integrations

    class NoDocConnector:
        def fetch_invoice_document(self, voucher_id):
            return None

    monkeypatch.setattr(integrations, "connector_for_integration", lambda *a: NoDocConnector())

    res = client.get(
        f"/api/v1/invoices/{voucher_seed['inv_a']}/document", headers=auth("tokA")
    )
    assert res.status_code == 404


def test_document_503s_when_credentials_cannot_be_decrypted(client, voucher_seed, monkeypatch):
    """A decrypt failure (e.g. a rotated encryption key) is our problem, not
    the caller's — it must not leak as a bare 500, and must not repeat the
    internal reason back to the client."""
    from web_api import integrations

    def _boom(*a):
        raise RuntimeError("Could not decrypt credentials for integration abc123")

    monkeypatch.setattr(integrations, "connector_for_integration", _boom)

    res = client.get(
        f"/api/v1/invoices/{voucher_seed['inv_a']}/document", headers=auth("tokA")
    )
    assert res.status_code == 503
    assert "decrypt" not in res.text.lower()


def test_document_404s_when_the_matching_entry_belongs_to_another_company(client, seed, engine):
    """A bad sync row — an entry whose account belongs to a different tenant's
    integration — must not let this endpoint reach that tenant's ERP. The
    company check has to reject the mismatch, not just trust the entry."""
    with Session(engine) as s:
        integ_b = ErpIntegration(
            company_id=seed["comp_b"], erp_type="mock", label="Org B's ERP",
            connected_at=datetime.now(timezone.utc),
        )
        s.add(integ_b)
        s.commit()
        account_b = ErpAccount(
            erp_integration_id=integ_b.id, erp_account_code="9999",
            erp_account_name="Foreign account", erp_account_type="expense",
        )
        s.add(account_b)
        s.commit()
        # company_id correctly says Org A, but the account it posts to belongs
        # to Org B's integration — the scenario the fix has to reject.
        bad_entry = ErpEntry(
            company_id=seed["comp_a"], erp_account_id=account_b.id,
            source_invoice_id=seed["inv_a"], voucher_id="9999",
            entry_type="purchase_invoice", accounting_date=date(2025, 7, 1),
            debit_amount=Decimal("5.00"), currency="DKK",
        )
        s.add(bad_entry)
        s.commit()
        file_row = File(
            company_id=seed["comp_a"], filename="x.pdf",
            file_type="invoice_pdf", storage_path="x.pdf",
        )
        s.add(file_row)
        s.commit()
        invoice = s.get(Invoice, seed["inv_a"])
        invoice.file_id = file_row.id
        s.add(invoice)
        s.commit()

    res = client.get(f"/api/v1/invoices/{seed['inv_a']}/document", headers=auth("tokA"))
    assert res.status_code == 404


def test_document_404s_when_the_owning_integration_is_disconnected(client, seed, engine):
    """A disconnected integration is a 404, not a cue to ask a *different*
    integration with the invoice's number as a guessed voucher id."""
    with Session(engine) as s:
        integ = ErpIntegration(
            company_id=seed["comp_a"], erp_type="mock", label="Disconnected ERP",
            connected_at=datetime.now(timezone.utc),
            disconnected_at=datetime.now(timezone.utc),
        )
        s.add(integ)
        s.commit()
        account = ErpAccount(
            erp_integration_id=integ.id, erp_account_code="6200",
            erp_account_name="Software", erp_account_type="expense",
        )
        s.add(account)
        s.commit()
        entry = ErpEntry(
            company_id=seed["comp_a"], erp_account_id=account.id,
            source_invoice_id=seed["inv_a"], voucher_id="4821",
            entry_type="purchase_invoice", accounting_date=date(2025, 7, 1),
            debit_amount=Decimal("100.00"), currency="DKK",
        )
        s.add(entry)
        s.commit()
        file_row = File(
            company_id=seed["comp_a"], filename="x.pdf",
            file_type="invoice_pdf", storage_path="x.pdf",
        )
        s.add(file_row)
        s.commit()
        invoice = s.get(Invoice, seed["inv_a"])
        invoice.file_id = file_row.id
        s.add(invoice)
        s.commit()

    res = client.get(f"/api/v1/invoices/{seed['inv_a']}/document", headers=auth("tokA"))
    assert res.status_code == 404
