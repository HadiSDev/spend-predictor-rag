"""The invoice document endpoint: live ERP fetch, tenant scoping and error mapping."""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlmodel import Session

from web_api import integrations
from web_api.connectors.base import ErpConnectionError
from web_api.db.models import ErpAccount, ErpEntry, ErpIntegration, File, Invoice
from web_api_testkit import auth


class _DeadConnector:
    def fetch_invoice_document(self, voucher_id):
        raise ErpConnectionError("connection refused: internal-erp-host.local:5432")


class _NoDocConnector:
    def fetch_invoice_document(self, voucher_id):
        return None


def test_document_404s_when_no_file_is_attached(client, seed):
    res = client.get(f"/api/v1/invoices/{seed['inv_a']}/document", headers=auth("tokA"))
    assert res.status_code == 404


def test_document_is_tenant_scoped(client, seed):
    res = client.get(f"/api/v1/invoices/{seed['inv_b']}/document", headers=auth("tokA"))
    assert res.status_code == 404


def test_invoice_read_reports_whether_a_document_exists(client, seed):
    body = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA")).json()
    assert body["has_document"] is False
    assert body["file_id"] is None


def test_document_502s_when_the_erp_is_unreachable(client, voucher_seed, monkeypatch):
    monkeypatch.setattr(integrations, "connector_for_integration", lambda *a: _DeadConnector())

    res = client.get(
        f"/api/v1/invoices/{voucher_seed['inv_a']}/document", headers=auth("tokA")
    )
    assert res.status_code == 502
    assert "internal-erp-host" not in res.text


def test_document_404s_when_the_erp_has_no_document_for_the_voucher(
    client, voucher_seed, monkeypatch
):
    monkeypatch.setattr(integrations, "connector_for_integration", lambda *a: _NoDocConnector())

    res = client.get(
        f"/api/v1/invoices/{voucher_seed['inv_a']}/document", headers=auth("tokA")
    )
    assert res.status_code == 404


def test_document_503s_when_credentials_cannot_be_decrypted(client, voucher_seed, monkeypatch):
    def _boom(*a):
        raise RuntimeError("Could not decrypt credentials for integration abc123")

    monkeypatch.setattr(integrations, "connector_for_integration", _boom)

    res = client.get(
        f"/api/v1/invoices/{voucher_seed['inv_a']}/document", headers=auth("tokA")
    )
    assert res.status_code == 503
    assert "decrypt" not in res.text.lower()


def test_document_404s_when_the_matching_entry_belongs_to_another_company(client, seed, engine):
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
