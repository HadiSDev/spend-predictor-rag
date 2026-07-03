"""ERP integration controller: CRUD, credentials, actions, account toggle."""
from __future__ import annotations

import pytest

from web_api import config as web_config
from web_api import credentials
from web_api.connectors import register_connector
from web_api.connectors.base import ErpAccountData, ErpConnector
from web_api.db.models import ErpCredential
from sqlmodel import Session, select
from .conftest import auth

SECRET = "super-secret-key-value"


# -- Fake connectors registered for the tests --------------------------------

class _FakeConn(ErpConnector):
    """Reachable ERP whose account chart can grow between calls."""

    accounts: list[ErpAccountData] = [
        ErpAccountData(erp_account_code="6010", erp_account_name="Cloud", erp_account_type="expense", with_vat=True),
        ErpAccountData(erp_account_code="6020", erp_account_name="Software", erp_account_type="expense", with_vat=True),
    ]

    def authorize(self) -> str:
        return "t"

    def test_connection(self) -> bool:
        return True

    def fetch_accounts(self):
        return list(type(self).accounts)

    def fetch_vendors(self, since=None):
        return []

    def fetch_invoices(self, since=None):
        return []

    def fetch_entries(self, since=None, account_codes=None):
        return []

    def fetch_invoice_scan(self, voucher_id):
        return None


class _BadConn(_FakeConn):
    def test_connection(self) -> bool:
        raise RuntimeError("boom: unreachable")


register_connector("faketest", _FakeConn)
register_connector("faketest_bad", _BadConn)


@pytest.fixture(autouse=True)
def _enc_key(monkeypatch):
    monkeypatch.setattr(web_config, "WEB_API_CREDENTIAL_ENC_KEY", credentials.generate_key())


def _create(client, token, company_id, erp_type="faketest", creds=None):
    return client.post("/api/v1/erp-integrations", headers=auth(token), json={
        "company_id": company_id, "erp_type": erp_type, "label": "Main",
        "credentials": creds if creds is not None else {"base_url": "http://x", "api_key": SECRET},
    })


# -- Create ------------------------------------------------------------------

def test_create_stores_encrypted_credentials(client, seed, engine):
    r = _create(client, "tokA", seed["comp_a"])
    assert r.status_code == 201
    body = r.json()
    assert body["has_credentials"] is True
    assert SECRET not in r.text  # secret never returned
    with Session(engine) as s:
        cred = s.exec(select(ErpCredential).where(
            ErpCredential.erp_integration_id == body["id"])).one()
        assert SECRET not in cred.encrypted_config          # stored encrypted
        assert credentials.decrypt_config(cred.encrypted_config)["api_key"] == SECRET


def test_create_unknown_erp_type_rejected(client, seed):
    r = _create(client, "tokA", seed["comp_a"], erp_type="does-not-exist")
    assert r.status_code == 422


def test_create_requires_management(client, seed):
    r = _create(client, "tok_memberA", seed["comp_a"])
    assert r.status_code == 403


def test_create_out_of_scope_company_404(client, seed):
    r = _create(client, "tokA", seed["comp_b"])  # Org B company, tokA is Org A
    assert r.status_code == 404


# -- Read + isolation --------------------------------------------------------

def test_list_scoped_and_no_secrets(client, seed):
    _create(client, "tokA", seed["comp_a"])
    _create(client, "tok_sysadmin", seed["comp_b"])  # system admin can target Org B
    a = client.get("/api/v1/erp-integrations", headers=auth("tokA")).json()
    assert {i["company_id"] for i in a} == {seed["comp_a"]}
    assert "api_key" not in client.get("/api/v1/erp-integrations", headers=auth("tokA")).text
    b = client.get("/api/v1/erp-integrations", headers=auth("tokB")).json()
    assert {i["company_id"] for i in b} == {seed["comp_b"]}


def test_detail_out_of_scope_404(client, seed):
    iid = _create(client, "tok_sysadmin", seed["comp_b"]).json()["id"]
    r = client.get(f"/api/v1/erp-integrations/{iid}", headers=auth("tokA"))
    assert r.status_code == 404


# -- Update ------------------------------------------------------------------

def test_update_label_keeps_credentials(client, seed, engine):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    r = client.patch(f"/api/v1/erp-integrations/{iid}", headers=auth("tokA"),
                     json={"label": "Renamed"})
    assert r.status_code == 200 and r.json()["label"] == "Renamed"
    with Session(engine) as s:
        cred = s.exec(select(ErpCredential).where(ErpCredential.erp_integration_id == iid)).one()
        assert credentials.decrypt_config(cred.encrypted_config)["api_key"] == SECRET


def test_update_replaces_credentials(client, seed, engine):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    client.patch(f"/api/v1/erp-integrations/{iid}", headers=auth("tokA"),
                 json={"credentials": {"base_url": "http://y", "api_key": "new-secret"}})
    with Session(engine) as s:
        cred = s.exec(select(ErpCredential).where(ErpCredential.erp_integration_id == iid)).one()
        assert credentials.decrypt_config(cred.encrypted_config)["api_key"] == "new-secret"


# -- Disconnect / reconnect --------------------------------------------------

def test_disconnect_retains_accounts_then_reconnect(client, seed):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))
    d = client.post(f"/api/v1/erp-integrations/{iid}/disconnect", headers=auth("tokA")).json()
    assert d["disconnected_at"] is not None
    # accounts retained
    accts = client.get(f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()
    assert len(accts) == 2
    # excluded from default listing, present with include_disconnected
    assert iid not in {i["id"] for i in client.get("/api/v1/erp-integrations", headers=auth("tokA")).json()}
    assert iid in {i["id"] for i in client.get(
        "/api/v1/erp-integrations", headers=auth("tokA"), params={"include_disconnected": True}).json()}
    r = client.post(f"/api/v1/erp-integrations/{iid}/reconnect", headers=auth("tokA")).json()
    assert r["disconnected_at"] is None


# -- Connection test ---------------------------------------------------------

def test_connection_ok(client, seed):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    r = client.post(f"/api/v1/erp-integrations/{iid}/test-connection", headers=auth("tokA"))
    assert r.status_code == 200 and r.json()["ok"] is True


def test_connection_failure_is_200_not_500(client, seed):
    iid = _create(client, "tokA", seed["comp_a"], erp_type="faketest_bad").json()["id"]
    r = client.post(f"/api/v1/erp-integrations/{iid}/test-connection", headers=auth("tokA"))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and "boom" in body["message"]


# -- Refresh accounts --------------------------------------------------------

def test_refresh_adds_new_and_preserves_selection(client, seed, monkeypatch):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    first = client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA")).json()
    assert first == {"seen": 2, "added": 2}

    # Disable 6010, then the ERP gains a new account.
    accts = client.get(f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()
    a6010 = next(a for a in accts if a["erp_account_code"] == "6010")
    client.patch(f"/api/v1/erp-accounts/{a6010['id']}", headers=auth("tokA"),
                 json={"sync_enabled": False})
    monkeypatch.setattr(_FakeConn, "accounts", _FakeConn.accounts + [
        ErpAccountData(erp_account_code="6600", erp_account_name="Consulting",
                       erp_account_type="expense", with_vat=True)])

    second = client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA")).json()
    assert second == {"seen": 3, "added": 1}
    accts2 = client.get(f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()
    by_code = {a["erp_account_code"]: a for a in accts2}
    assert set(by_code) == {"6010", "6020", "6600"}
    assert by_code["6010"]["sync_enabled"] is False   # selection preserved


# -- Account toggle ----------------------------------------------------------

def test_account_toggle_and_scope(client, seed):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))
    acct = client.get(f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()[0]

    r = client.patch(f"/api/v1/erp-accounts/{acct['id']}", headers=auth("tokA"),
                     json={"sync_enabled": False, "with_vat": False})
    assert r.status_code == 200
    assert r.json()["sync_enabled"] is False and r.json()["with_vat"] is False

    # A non-manager is refused (403) before any scope check — same for a member of
    # another org (the management gate runs first, without leaking existence).
    assert client.patch(f"/api/v1/erp-accounts/{acct['id']}", headers=auth("tok_memberA"),
                        json={"sync_enabled": True}).status_code == 403
    assert client.patch(f"/api/v1/erp-accounts/{acct['id']}", headers=auth("tokB"),
                        json={"sync_enabled": True}).status_code == 403
    # Read path is tenant-scoped: another org's member cannot even see the accounts.
    assert client.get(f"/api/v1/erp-integrations/{iid}/accounts",
                      headers=auth("tokB")).status_code == 404
