from .conftest import auth


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
            raise ErpConnectionError("connection refused")

    monkeypatch.setattr(integrations, "connector_for_integration", lambda *a: DeadConnector())

    res = client.get(
        f"/api/v1/invoices/{voucher_seed['inv_a']}/document", headers=auth("tokA")
    )
    assert res.status_code == 502
