"""ERP integration controller: CRUD, credentials, actions, account toggle."""
from __future__ import annotations

import pytest

from web_api import config as web_config
from web_api import credentials
from web_api.connectors import register_connector
from web_api.connectors.base import CredentialField, DocumentPayload, ErpAccountData, ErpConnector
from web_api.db.models import ErpCredential
from sqlmodel import Session, select
from .conftest import auth

SECRET = "super-secret-key-value"


# -- Fake connectors registered for the tests --------------------------------

class _FakeConn(ErpConnector):
    """Reachable ERP whose account chart can grow between calls."""

    display_label = "Fake ERP"
    # Credentials are validated against these, so the fake declares what it takes.
    credential_fields = [
        CredentialField(name="base_url", label="Base URL", required=True),
        CredentialField(name="api_key", label="API key", secret=True),
    ]

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

    def fetch_invoice_document(self, voucher_id):
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


def test_create_missing_required_credential_rejected(client, seed):
    # base_url is required on the fake connector; blank is as absent as missing.
    r = _create(client, "tokA", seed["comp_a"], creds={"api_key": SECRET})
    assert r.status_code == 422
    assert "base_url" in r.text
    assert _create(client, "tokA", seed["comp_a"],
                   creds={"base_url": "  ", "api_key": SECRET}).status_code == 422


def test_create_undeclared_credential_key_rejected(client, seed, engine):
    r = _create(client, "tokA", seed["comp_a"],
                creds={"base_url": "http://x", "apikey": SECRET})  # typo'd key
    assert r.status_code == 422
    assert "apikey" in r.text
    with Session(engine) as s:
        assert s.exec(select(ErpCredential)).all() == []


def test_update_undeclared_credential_key_rejected(client, seed, engine):
    integration_id = _create(client, "tokA", seed["comp_a"]).json()["id"]
    r = client.patch(f"/api/v1/erp-integrations/{integration_id}", headers=auth("tokA"),
                     json={"credentials": {"base_url": "http://y", "apikey": "x"}})
    assert r.status_code == 422
    with Session(engine) as s:  # the original credential is untouched
        cred = s.exec(select(ErpCredential).where(
            ErpCredential.erp_integration_id == integration_id)).one()
        assert credentials.decrypt_config(cred.encrypted_config)["api_key"] == SECRET


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


def test_refresh_preserves_a_customers_vat_setting(client, seed, monkeypatch):
    """`with_vat` is the customer's assumption, not the ERP's fact.

    It decides whether a parsed invoice is read as VAT-inclusive when
    reconciling, so a refresh that reset it would discard a judgement someone
    made — silently, and only visibly much later as a wrong comparison.
    """
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))
    accts = client.get(f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()
    a6010 = next(a for a in accts if a["erp_account_code"] == "6010")
    assert a6010["with_vat"] is True   # seeded from the ERP

    # The customer disagrees with the ERP.
    client.patch(f"/api/v1/erp-accounts/{a6010['id']}", headers=auth("tokA"),
                 json={"with_vat": False})
    # ...and the ERP still insists, while renaming the account.
    monkeypatch.setattr(_FakeConn, "accounts", [
        ErpAccountData(erp_account_code="6010", erp_account_name="Cloud Hosting (renamed)",
                       erp_account_type="expense", with_vat=True),
        ErpAccountData(erp_account_code="6020", erp_account_name="Software",
                       erp_account_type="expense", with_vat=True),
    ])
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))

    after = {a["erp_account_code"]: a for a in client.get(
        f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()}
    assert after["6010"]["with_vat"] is False                        # ours stands
    assert after["6010"]["erp_account_name"] == "Cloud Hosting (renamed)"  # theirs refreshes


def test_a_newly_discovered_account_takes_the_erps_vat_value(client, seed, monkeypatch):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))

    monkeypatch.setattr(_FakeConn, "accounts", _FakeConn.accounts + [
        ErpAccountData(erp_account_code="1000", erp_account_name="Cash",
                       erp_account_type="asset", with_vat=False)])
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))

    after = {a["erp_account_code"]: a for a in client.get(
        f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()}
    assert after["1000"]["with_vat"] is False   # seeded, not defaulted
    assert after["6010"]["with_vat"] is True


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


# -- Connector catalog -------------------------------------------------------

def test_erp_types_lists_registered_connectors(client, seed):
    r = client.get("/api/v1/erp-types", headers=auth("tokA"))
    assert r.status_code == 200
    by_type = {t["erp_type"]: t for t in r.json()}

    mock = by_type["mock"]
    assert mock["label"] == "Debug ERP"
    fields = {f["name"]: f for f in mock["credential_fields"]}
    assert set(fields) == {"base_url", "api_key"}
    # Both optional with the defaults the connector already applies; only the key
    # is secret, and a descriptor carries no stored value.
    assert fields["base_url"] == {"name": "base_url", "label": "Base URL",
                                  "required": False, "secret": False,
                                  "default": "http://localhost:8001"}
    assert fields["api_key"]["secret"] is True
    assert fields["api_key"]["required"] is False

    # Registering a connector is all it takes to appear.
    assert by_type["faketest"]["label"] == "Fake ERP"


def test_erp_types_readable_by_any_authenticated_role(client, seed):
    # Not management-gated: it is not tenant data.
    for token in ("tok_viewerA", "tok_memberA", "tokA"):
        assert client.get("/api/v1/erp-types", headers=auth(token)).status_code == 200


def test_erp_types_requires_authentication(client, seed):
    assert client.get("/api/v1/erp-types").status_code == 401
    assert client.get("/api/v1/erp-types", headers=auth("bad-token")).status_code == 401


def test_erp_types_drive_valid_creation(client, seed):
    types = {t["erp_type"] for t in client.get(
        "/api/v1/erp-types", headers=auth("tokA")).json()}
    assert _create(client, "tokA", seed["comp_a"], erp_type="faketest").status_code == 201
    assert "not-a-connector" not in types
    assert _create(client, "tokA", seed["comp_a"],
                   erp_type="not-a-connector").status_code == 422
