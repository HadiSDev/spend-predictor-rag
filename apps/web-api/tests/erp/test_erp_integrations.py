"""ERP integration controller: CRUD, credentials, actions, account toggle."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlmodel import Session, select

from web_api import config as web_config
from web_api import credentials
from web_api.connectors import ErpAuthError, register_connector
from web_api.connectors.base import CredentialField, ErpAccountData, ErpConnector
from web_api.db.models import ErpAccount, ErpCredential, ErpEntry, Invoice
from web_api_testkit import auth

SECRET = "super-secret-key-value"


class _FakeConn(ErpConnector):
    """Reachable ERP whose account chart can grow between calls."""

    display_label = "Fake ERP"
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


class _BadAuthConn(_FakeConn):
    def test_connection(self) -> bool:
        raise ErpAuthError("token tok_secret_123 expired")


class _BrandedConn(_FakeConn):
    """Declares the optional brand metadata, so the catalog can project it."""

    display_label = "Branded ERP"
    brand_slug = "branded"
    description = "An ERP with a face."
    docs_url = "https://example.invalid/docs"


register_connector("faketest", _FakeConn)
register_connector("faketest_bad", _BadConn)
register_connector("faketest_branded", _BrandedConn)
register_connector("faketest_badauth", _BadAuthConn)


@pytest.fixture(autouse=True)
def _enc_key(monkeypatch):
    monkeypatch.setattr(web_config, "WEB_API_CREDENTIAL_ENC_KEY", credentials.generate_key())


def _create(client, token, company_id, erp_type="faketest", creds=None):
    return client.post("/api/v1/erp-integrations", headers=auth(token), json={
        "company_id": company_id, "erp_type": erp_type, "label": "Main",
        "credentials": creds if creds is not None else {"base_url": "http://x", "api_key": SECRET},
    })


def test_create_stores_encrypted_credentials(client, seed, engine):
    r = _create(client, "tokA", seed["comp_a"])
    assert r.status_code == 201
    body = r.json()
    assert body["has_credentials"] is True
    assert SECRET not in r.text
    with Session(engine) as s:
        cred = s.exec(select(ErpCredential).where(
            ErpCredential.erp_integration_id == body["id"])).one()
        assert SECRET not in cred.encrypted_config
        assert credentials.decrypt_config(cred.encrypted_config)["api_key"] == SECRET


def test_create_unknown_erp_type_rejected(client, seed):
    r = _create(client, "tokA", seed["comp_a"], erp_type="does-not-exist")
    assert r.status_code == 422


def test_create_missing_required_credential_rejected(client, seed):
    r = _create(client, "tokA", seed["comp_a"], creds={"api_key": SECRET})
    assert r.status_code == 422
    assert "base_url" in r.text
    assert _create(client, "tokA", seed["comp_a"],
                   creds={"base_url": "  ", "api_key": SECRET}).status_code == 422


def test_create_undeclared_credential_key_rejected(client, seed, engine):
    r = _create(client, "tokA", seed["comp_a"],
                creds={"base_url": "http://x", "apikey": SECRET})
    assert r.status_code == 422
    assert "apikey" in r.text
    with Session(engine) as s:
        assert s.exec(select(ErpCredential)).all() == []


def test_update_undeclared_credential_key_rejected(client, seed, engine):
    integration_id = _create(client, "tokA", seed["comp_a"]).json()["id"]
    r = client.patch(f"/api/v1/erp-integrations/{integration_id}", headers=auth("tokA"),
                     json={"credentials": {"base_url": "http://y", "apikey": "x"}})
    assert r.status_code == 422
    with Session(engine) as s:
        cred = s.exec(select(ErpCredential).where(
            ErpCredential.erp_integration_id == integration_id)).one()
        assert credentials.decrypt_config(cred.encrypted_config)["api_key"] == SECRET


def test_create_requires_management(client, seed):
    r = _create(client, "tok_memberA", seed["comp_a"])
    assert r.status_code == 403


def test_create_out_of_scope_company_404(client, seed):
    r = _create(client, "tokA", seed["comp_b"])
    assert r.status_code == 404


def test_list_scoped_and_no_secrets(client, seed):
    _create(client, "tokA", seed["comp_a"])
    _create(client, "tok_sysadmin", seed["comp_b"])
    a = client.get("/api/v1/erp-integrations", headers=auth("tokA")).json()
    assert {i["company_id"] for i in a} == {seed["comp_a"]}
    assert "api_key" not in client.get("/api/v1/erp-integrations", headers=auth("tokA")).text
    b = client.get("/api/v1/erp-integrations", headers=auth("tokB")).json()
    assert {i["company_id"] for i in b} == {seed["comp_b"]}


def test_detail_out_of_scope_404(client, seed):
    iid = _create(client, "tok_sysadmin", seed["comp_b"]).json()["id"]
    r = client.get(f"/api/v1/erp-integrations/{iid}", headers=auth("tokA"))
    assert r.status_code == 404


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


def test_disconnect_retains_accounts_then_reconnect(client, seed):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))
    d = client.post(f"/api/v1/erp-integrations/{iid}/disconnect", headers=auth("tokA")).json()
    assert d["disconnected_at"] is not None
    accts = client.get(f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()
    assert len(accts) == 2
    assert iid not in {i["id"] for i in client.get("/api/v1/erp-integrations", headers=auth("tokA")).json()}
    assert iid in {i["id"] for i in client.get(
        "/api/v1/erp-integrations", headers=auth("tokA"), params={"include_disconnected": True}).json()}
    r = client.post(f"/api/v1/erp-integrations/{iid}/reconnect", headers=auth("tokA")).json()
    assert r["disconnected_at"] is None


def test_connection_ok(client, seed):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    r = client.post(f"/api/v1/erp-integrations/{iid}/test-connection", headers=auth("tokA"))
    assert r.status_code == 200 and r.json()["ok"] is True


def test_connection_failure_is_200_not_500(client, seed):
    iid = _create(client, "tokA", seed["comp_a"], erp_type="faketest_bad").json()["id"]
    r = client.post(f"/api/v1/erp-integrations/{iid}/test-connection", headers=auth("tokA"))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["message"] == "Connection test failed"
    assert "boom" not in body["message"]


def test_connection_failure_names_rejected_credentials(client, seed):
    iid = _create(client, "tokA", seed["comp_a"], erp_type="faketest_badauth").json()["id"]
    r = client.post(f"/api/v1/erp-integrations/{iid}/test-connection", headers=auth("tokA"))
    assert r.status_code == 200
    assert r.json() == {"ok": False, "message": "The ERP rejected the credentials"}


def test_refresh_adds_new_and_preserves_selection(client, seed, monkeypatch):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    first = client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA")).json()
    assert first == {"seen": 2, "added": 2}

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
    assert by_code["6010"]["sync_enabled"] is False


def test_refresh_preserves_a_customers_vat_setting(client, seed, monkeypatch):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))
    accts = client.get(f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()
    a6010 = next(a for a in accts if a["erp_account_code"] == "6010")
    assert a6010["with_vat"] is True

    client.patch(f"/api/v1/erp-accounts/{a6010['id']}", headers=auth("tokA"),
                 json={"with_vat": False})
    monkeypatch.setattr(_FakeConn, "accounts", [
        ErpAccountData(erp_account_code="6010", erp_account_name="Cloud Hosting (renamed)",
                       erp_account_type="expense", with_vat=True),
        ErpAccountData(erp_account_code="6020", erp_account_name="Software",
                       erp_account_type="expense", with_vat=True),
    ])
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))

    after = {a["erp_account_code"]: a for a in client.get(
        f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()}
    assert after["6010"]["with_vat"] is False
    assert after["6010"]["erp_account_name"] == "Cloud Hosting (renamed)"


def test_a_newly_discovered_account_takes_the_erps_vat_value(client, seed, monkeypatch):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))

    monkeypatch.setattr(_FakeConn, "accounts", _FakeConn.accounts + [
        ErpAccountData(erp_account_code="1000", erp_account_name="Cash",
                       erp_account_type="asset", with_vat=False)])
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))

    after = {a["erp_account_code"]: a for a in client.get(
        f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()}
    assert after["1000"]["with_vat"] is False
    assert after["6010"]["with_vat"] is True


def test_account_toggle_and_scope(client, seed):
    iid = _create(client, "tokA", seed["comp_a"]).json()["id"]
    client.post(f"/api/v1/erp-integrations/{iid}/refresh-accounts", headers=auth("tokA"))
    acct = client.get(f"/api/v1/erp-integrations/{iid}/accounts", headers=auth("tokA")).json()[0]

    r = client.patch(f"/api/v1/erp-accounts/{acct['id']}", headers=auth("tokA"),
                     json={"sync_enabled": False, "with_vat": False})
    assert r.status_code == 200
    assert r.json()["sync_enabled"] is False and r.json()["with_vat"] is False

    assert client.patch(f"/api/v1/erp-accounts/{acct['id']}", headers=auth("tok_memberA"),
                        json={"sync_enabled": True}).status_code == 403
    assert client.patch(f"/api/v1/erp-accounts/{acct['id']}", headers=auth("tokB"),
                        json={"sync_enabled": True}).status_code == 403
    assert client.get(f"/api/v1/erp-integrations/{iid}/accounts",
                      headers=auth("tokB")).status_code == 404


def test_erp_types_lists_registered_connectors(client, seed):
    r = client.get("/api/v1/erp-types", headers=auth("tokA"))
    assert r.status_code == 200
    by_type = {t["erp_type"]: t for t in r.json()}

    mock = by_type["mock"]
    assert mock["label"] == "Debug ERP"
    fields = {f["name"]: f for f in mock["credential_fields"]}
    assert set(fields) == {"base_url", "api_key"}
    assert fields["base_url"] == {"name": "base_url", "label": "Base URL",
                                  "required": False, "secret": False,
                                  "default": "http://localhost:8001"}
    assert fields["api_key"]["secret"] is True
    assert fields["api_key"]["required"] is False

    assert by_type["faketest"]["label"] == "Fake ERP"


def test_erp_types_projects_brand_metadata_when_a_connector_declares_it(client, seed):
    by_type = {t["erp_type"]: t
               for t in client.get("/api/v1/erp-types", headers=auth("tokA")).json()}

    branded = by_type["faketest_branded"]
    assert branded["brand_slug"] == "branded"
    assert branded["description"] == "An ERP with a face."
    assert branded["docs_url"] == "https://example.invalid/docs"


def test_erp_types_entry_is_unchanged_for_a_connector_declaring_no_brand(client, seed):
    by_type = {t["erp_type"]: t
               for t in client.get("/api/v1/erp-types", headers=auth("tokA")).json()}

    plain = by_type["faketest"]
    assert plain["label"] == "Fake ERP"
    assert {f["name"] for f in plain["credential_fields"]} == {"base_url", "api_key"}
    assert plain["brand_slug"] is None
    assert plain["description"] is None
    assert plain["docs_url"] is None


def test_erp_types_offers_billy_with_its_brand_and_credentials(client, seed):
    by_type = {t["erp_type"]: t
               for t in client.get("/api/v1/erp-types", headers=auth("tokA")).json()}

    billy = by_type["billy"]
    assert billy["label"] == "Billy"
    assert billy["brand_slug"] == "billy"
    assert billy["description"] and billy["docs_url"]

    fields = {f["name"]: f for f in billy["credential_fields"]}
    assert set(fields) == {"access_token", "organization_id", "base_url"}
    assert fields["access_token"]["required"] is True
    assert fields["access_token"]["secret"] is True
    assert fields["organization_id"]["required"] is False
    assert fields["base_url"]["default"] == "https://api.billysbilling.com/v2"
    assert "password" not in fields


def test_billy_integration_requires_its_access_token(client, seed):
    ok = _create(client, "tokA", seed["comp_a"], erp_type="billy",
                 creds={"access_token": SECRET})
    assert ok.status_code == 201
    assert ok.json()["has_credentials"] is True
    assert "credentials" not in ok.json()

    missing = _create(client, "tokA", seed["comp_a"], erp_type="billy", creds={})
    assert missing.status_code == 422


def test_billy_integration_rejects_a_password_credential(client, seed):
    r = _create(client, "tokA", seed["comp_a"], erp_type="billy",
                creds={"access_token": SECRET, "password": "hunter2"})
    assert r.status_code == 422


def test_erp_types_readable_by_any_authenticated_role(client, seed):
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


def test_replace_disconnects_the_old_and_connects_the_new(client, engine):
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Switcher",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()
    old_id = company["integration"]["id"]

    response = client.post(
        f"/api/v1/erp-integrations/{old_id}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "label": "Billy main",
              "credentials": {"access_token": "tok_live"}},
    )

    assert response.status_code == 201, response.text
    new = response.json()
    assert new["id"] != old_id
    assert new["erp_type"] == "billy"
    assert new["label"] == "Billy main"
    assert new["has_credentials"] is True
    assert new["disconnected_at"] is None

    old = client.get(f"/api/v1/erp-integrations/{old_id}", headers=auth("tokA")).json()
    assert old["disconnected_at"] is not None, "the outgoing integration must be retired"


def test_replacing_with_the_same_erp_type_is_422(client):
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Same",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()
    integration_id = company["integration"]["id"]

    response = client.post(
        f"/api/v1/erp-integrations/{integration_id}/replace",
        headers=auth("tokA"),
        json={"erp_type": "mock", "credentials": {}},
    )

    assert response.status_code == 422
    assert "PATCH" in response.json()["detail"]


def test_a_rejected_replacement_leaves_the_old_integration_connected(client):
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Rollback",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()
    old_id = company["integration"]["id"]

    response = client.post(
        f"/api/v1/erp-integrations/{old_id}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "credentials": {"nonsense_key": "x"}},
    )
    assert response.status_code == 422

    old = client.get(f"/api/v1/erp-integrations/{old_id}", headers=auth("tokA")).json()
    assert old["disconnected_at"] is None, "a rejected switch must change nothing"

    listed = client.get("/api/v1/erp-integrations", headers=auth("tokA")).json()
    assert [i["id"] for i in listed if i["company_id"] == company["id"]] == [old_id]


def test_replace_requires_a_management_role(client):
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Gated",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()

    response = client.post(
        f"/api/v1/erp-integrations/{company['integration']['id']}/replace",
        headers=auth("tok_viewerA"),
        json={"erp_type": "billy", "credentials": {"access_token": "t"}},
    )
    assert response.status_code == 403


@pytest.fixture
def seed_switchable_ledger(client, engine):
    """A company + integration with ledger history, and the counts to expect."""

    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Historied",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()
    integration_id = company["integration"]["id"]

    with Session(engine) as session:
        account = ErpAccount(
            erp_integration_id=integration_id,
            erp_account_code="6000",
            erp_account_name="Consulting",
        )
        session.add(account)
        invoices = []
        for n in (1, 2):
            invoice = Invoice(company_id=company["id"], status="uncategorized", source="erp")
            invoices.append(invoice)
            session.add(invoice)
        session.add_all(
            [
                ErpEntry(
                    company_id=company["id"],
                    erp_account_id=account.id,
                    source_invoice_id=invoices[0].id,
                    entry_type="purchase_invoice",
                    accounting_date=dt.date(2026, 1, 5),
                ),
                ErpEntry(
                    company_id=company["id"],
                    erp_account_id=account.id,
                    source_invoice_id=invoices[1].id,
                    entry_type="purchase_invoice",
                    accounting_date=dt.date(2026, 3, 20),
                ),
                ErpEntry(
                    company_id=company["id"],
                    erp_account_id=account.id,
                    source_invoice_id=None,
                    entry_type="journal_entry",
                    accounting_date=dt.date(2026, 2, 1),
                ),
            ]
        )
        session.commit()

    return integration_id, {"entries": 3, "invoices": 2}


def test_replace_409s_with_counts_when_the_old_integration_has_ledger_data(
    client, engine, seed_switchable_ledger
):
    old_id, expected = seed_switchable_ledger

    response = client.post(
        f"/api/v1/erp-integrations/{old_id}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "credentials": {"access_token": "t"}},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["entries"] == expected["entries"]
    assert detail["invoices"] == expected["invoices"]
    assert detail["earliest"] == "2026-01-05"
    assert detail["latest"] == "2026-03-20"

    old = client.get(f"/api/v1/erp-integrations/{old_id}", headers=auth("tokA")).json()
    assert old["disconnected_at"] is None, "a blocked switch must change nothing"


def test_replace_proceeds_with_confirm_true(client, seed_switchable_ledger):
    old_id, _ = seed_switchable_ledger

    response = client.post(
        f"/api/v1/erp-integrations/{old_id}/replace",
        headers=auth("tokA"),
        json={
            "erp_type": "billy",
            "credentials": {"access_token": "t"},
            "confirm": True,
        },
    )

    assert response.status_code == 201, response.text
    old = client.get(f"/api/v1/erp-integrations/{old_id}", headers=auth("tokA")).json()
    assert old["disconnected_at"] is not None


def test_replace_needs_no_confirmation_when_nothing_was_synced(client):
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Fresh",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()

    response = client.post(
        f"/api/v1/erp-integrations/{company['integration']['id']}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "credentials": {"access_token": "t"}},
    )
    assert response.status_code == 201, response.text


def test_replace_on_an_already_retired_integration_is_422(client):
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Doubled",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()
    old_id = company["integration"]["id"]

    first = client.post(
        f"/api/v1/erp-integrations/{old_id}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "credentials": {"access_token": "t"}},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"/api/v1/erp-integrations/{old_id}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "credentials": {"access_token": "t2"}},
    )
    assert second.status_code == 422
    assert "retired" in second.json()["detail"].lower()

    listed = client.get("/api/v1/erp-integrations", headers=auth("tokA")).json()
    live = [i for i in listed if i["company_id"] == company["id"]]
    assert len(live) == 1
    assert live[0]["id"] == first.json()["id"]


def test_replace_validates_credentials_before_reporting_the_ledger_count(
    client, seed_switchable_ledger
):
    old_id, _ = seed_switchable_ledger

    response = client.post(
        f"/api/v1/erp-integrations/{old_id}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "credentials": {}},
    )
    assert response.status_code == 422
    assert "access_token" in response.json()["detail"]

    old = client.get(f"/api/v1/erp-integrations/{old_id}", headers=auth("tokA")).json()
    assert old["disconnected_at"] is None, "an invalid replace must change nothing"


def test_replace_on_another_orgs_integration_is_404(client, seed):
    iid = _create(client, "tok_sysadmin", seed["comp_b"]).json()["id"]

    response = client.post(
        f"/api/v1/erp-integrations/{iid}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "credentials": {"access_token": "t"}},
    )
    assert response.status_code == 404
