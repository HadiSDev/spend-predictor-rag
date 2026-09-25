"""Company & organization management: authorization matrix, CRUD, cross-tenant."""
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from web_api import config as web_config
from web_api import credentials
from web_api.db.models import (
    Company,
    ErpCredential,
    ErpIntegration,
    Invoice,
    Organization,
    User,
)
from web_api_testkit import auth


MINIMAL_INTEGRATION = {"erp_type": "mock"}


def _create(client, token, **body):
    return client.post("/api/v1/companies", headers=auth(token),
                       json={"name": "NewCo", "base_currency": "DKK",
                             "integration": MINIMAL_INTEGRATION, **body})


@pytest.mark.parametrize("token", ["tokA", "tok_moderatorA", "tok_sysadmin"])
def test_managers_can_create_company(client, token):
    assert _create(client, token).status_code == 201


@pytest.mark.parametrize("token", ["tok_memberA", "tok_viewerA"])
def test_non_managers_cannot_create_company(client, token):
    assert _create(client, token).status_code == 403


def test_create_returns_company_under_callers_org(client):
    r = _create(client, "tokA", country_code="DK")
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "NewCo"
    assert body["country_code"] == "DK"
    assert body["is_active"] is True
    names = [c["name"] for c in client.get("/api/v1/companies", headers=auth("tokA")).json()]
    assert "NewCo" in names


def test_create_returns_and_persists_the_integration(client, engine):
    body = _create(client, "tokA").json()
    integration = body["integration"]
    assert integration["erp_type"] == "mock"
    assert integration["company_id"] == body["id"]
    assert integration["connected_at"] is not None
    assert integration["has_credentials"] is False

    with Session(engine) as s:
        rows = s.exec(select(ErpIntegration).where(
            ErpIntegration.company_id == body["id"])).all()
        assert [r.erp_type for r in rows] == ["mock"]
        assert s.exec(select(ErpCredential)).all() == []

    listed = client.get("/api/v1/erp-integrations", headers=auth("tokA"),
                        params={"company_id": body["id"]}).json()
    assert [i["id"] for i in listed] == [integration["id"]]


def test_create_with_credentials_stores_them_encrypted(client, engine, monkeypatch):
    monkeypatch.setattr(web_config, "WEB_API_CREDENTIAL_ENC_KEY", credentials.generate_key())
    secret = "company-create-secret"
    r = client.post("/api/v1/companies", headers=auth("tokA"), json={
        "name": "WithCreds",
        "base_currency": "DKK",
        "integration": {"erp_type": "mock", "label": "Main",
                        "credentials": {"base_url": "http://x", "api_key": secret}},
    })
    assert r.status_code == 201
    assert r.json()["integration"]["has_credentials"] is True
    assert secret not in r.text
    with Session(engine) as s:
        cred = s.exec(select(ErpCredential)).one()
        assert secret not in cred.encrypted_config
        assert credentials.decrypt_config(cred.encrypted_config)["api_key"] == secret


def test_create_requires_name(client):
    r = client.post("/api/v1/companies", headers=auth("tokA"),
                    json={"base_currency": "DKK", "integration": MINIMAL_INTEGRATION})
    assert r.status_code == 422


def test_create_requires_an_integration(client, engine):
    r = client.post("/api/v1/companies", headers=auth("tokA"), json={"name": "Bare", "base_currency": "DKK"})
    assert r.status_code == 422
    with Session(engine) as s:
        assert s.exec(select(Company).where(Company.name == "Bare")).all() == []


def test_create_with_unknown_erp_type_creates_nothing(client, engine):
    r = client.post("/api/v1/companies", headers=auth("tokA"),
                    json={"name": "Nope", "base_currency": "DKK",
                          "integration": {"erp_type": "does-not-exist"}})
    assert r.status_code == 422
    with Session(engine) as s:
        assert s.exec(select(Company).where(Company.name == "Nope")).all() == []
        assert s.exec(select(ErpIntegration)).all() == []


def test_create_rolls_the_company_back_when_the_integration_fails(client, engine, monkeypatch):
    monkeypatch.setattr(web_config, "WEB_API_CREDENTIAL_ENC_KEY", "")
    r = client.post("/api/v1/companies", headers=auth("tokA"), json={
        "name": "Doomed",
        "base_currency": "DKK",
        "integration": {"erp_type": "mock", "credentials": {"api_key": "x"}},
    })
    assert r.status_code == 500
    with Session(engine) as s:
        assert s.exec(select(Company).where(Company.name == "Doomed")).all() == []
        assert s.exec(select(ErpIntegration)).all() == []


def test_update_company(client):
    cid = _create(client, "tok_moderatorA").json()["id"]
    r = client.patch(f"/api/v1/companies/{cid}", headers=auth("tok_moderatorA"),
                     json={"vat_number": "DK12345678"})
    assert r.status_code == 200
    assert r.json()["vat_number"] == "DK12345678"


def test_update_foreign_company_is_404(client, seed):
    r = client.patch(f"/api/v1/companies/{seed['comp_b']}", headers=auth("tokA"),
                     json={"name": "hijack"})
    assert r.status_code == 404


def test_deactivate_hides_from_default_list_and_activate_restores(client):
    cid = _create(client, "tokA").json()["id"]

    d = client.post(f"/api/v1/companies/{cid}/deactivate", headers=auth("tokA"))
    assert d.status_code == 200
    assert d.json()["is_active"] is False
    assert d.json()["deactivated_at"] is not None

    default_ids = [c["id"] for c in client.get("/api/v1/companies", headers=auth("tokA")).json()]
    assert cid not in default_ids
    all_ids = [c["id"] for c in client.get(
        "/api/v1/companies", headers=auth("tokA"), params={"include_inactive": True}).json()]
    assert cid in all_ids

    a = client.post(f"/api/v1/companies/{cid}/activate", headers=auth("tokA"))
    assert a.status_code == 200
    assert a.json()["is_active"] is True and a.json()["deactivated_at"] is None
    assert cid in [c["id"] for c in client.get("/api/v1/companies", headers=auth("tokA")).json()]


def test_system_admin_creates_company_in_another_org(client, seed):
    r = client.post("/api/v1/companies", headers=auth("tok_sysadmin"),
                    json={"name": "CrossOrgCo", "organization_id": seed["org_b"],
                          "base_currency": "DKK",
                          "integration": MINIMAL_INTEGRATION})
    assert r.status_code == 201
    names = [c["name"] for c in client.get("/api/v1/companies", headers=auth("tokB")).json()]
    assert "CrossOrgCo" in names


def test_non_admin_cannot_target_another_org(client, seed):
    r = client.post("/api/v1/companies", headers=auth("tokA"),
                    json={"name": "Nope", "organization_id": seed["org_b"],
                          "base_currency": "DKK",
                          "integration": MINIMAL_INTEGRATION})
    assert r.status_code == 403


def test_get_organization_returns_own(client):
    r = client.get("/api/v1/organization", headers=auth("tokA"))
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Org A"
    assert body["status"] == "active"


def test_admin_updates_org_moderator_cannot(client):
    ok = client.patch("/api/v1/organization", headers=auth("tokA"), json={"name": "Org A Renamed"})
    assert ok.status_code == 200
    assert ok.json()["name"] == "Org A Renamed"

    forbidden = client.patch("/api/v1/organization", headers=auth("tok_moderatorA"),
                             json={"name": "Mod Rename"})
    assert forbidden.status_code == 403


def test_duplicate_slug_is_409(client, engine, seed):
    with Session(engine) as s:
        org_b = s.get(Organization, seed["org_b"])
        org_b.slug = "taken"
        s.add(org_b)
        s.commit()
    r = client.patch("/api/v1/organization", headers=auth("tokA"), json={"slug": "taken"})
    assert r.status_code == 409


def test_moderator_role_is_provisioned(client, engine):
    client.get("/api/v1/organization", headers=auth("tok_moderatorA"))
    with Session(engine) as s:
        user = s.exec(select(User).where(User.clerk_user_id == "userMod")).one()
        assert user.role == "moderator"


def test_system_admin_flag_provisioned(client, engine):
    client.get("/api/v1/organization", headers=auth("tok_sysadmin"))
    client.get("/api/v1/organization", headers=auth("tokA"))
    with Session(engine) as s:
        sysadmin = s.exec(select(User).where(User.clerk_user_id == "userSys")).one()
        admin = s.exec(select(User).where(User.clerk_user_id == "userA")).one()
        assert sysadmin.is_system_admin is True
        assert admin.is_system_admin is False


def test_create_requires_a_base_currency(client, engine):
    r = client.post("/api/v1/companies", headers=auth("tokA"),
                    json={"name": "NoCurrency", "integration": MINIMAL_INTEGRATION})
    assert r.status_code == 422
    with Session(engine) as s:
        assert s.exec(select(Company).where(Company.name == "NoCurrency")).all() == []
        assert s.exec(select(ErpIntegration)).all() == []


@pytest.mark.parametrize("bad", ["kroner", "E", "DK1", "", "   "])
def test_create_with_an_invalid_currency_creates_nothing(client, engine, bad):
    r = client.post("/api/v1/companies", headers=auth("tokA"),
                    json={"name": "BadCurrency", "base_currency": bad,
                          "integration": MINIMAL_INTEGRATION})
    assert r.status_code == 422
    with Session(engine) as s:
        assert s.exec(select(Company).where(Company.name == "BadCurrency")).all() == []


def test_a_currency_code_is_stored_uppercased(client, engine):
    body = _create(client, "tokA", base_currency="dkk").json()
    assert body["base_currency"] == "DKK"
    with Session(engine) as s:
        assert s.get(Company, body["id"]).base_currency == "DKK"


def test_companies_report_their_base_currency(client):
    _create(client, "tokA", base_currency="SEK")
    companies = client.get("/api/v1/companies", headers=auth("tokA")).json()
    assert all("base_currency" in c for c in companies)
    assert "SEK" in [c["base_currency"] for c in companies]


def test_base_currency_can_be_changed(client):
    cid = _create(client, "tok_moderatorA", base_currency="DKK").json()["id"]

    r = client.patch(f"/api/v1/companies/{cid}", headers=auth("tok_moderatorA"),
                     json={"base_currency": "eur"})

    assert r.status_code == 200
    assert r.json()["base_currency"] == "EUR"


def test_an_invalid_currency_leaves_the_company_alone(client):
    cid = _create(client, "tokA", base_currency="DKK").json()["id"]

    r = client.patch(f"/api/v1/companies/{cid}", headers=auth("tokA"),
                     json={"base_currency": "E"})

    assert r.status_code == 422
    current = client.get("/api/v1/companies", headers=auth("tokA")).json()
    assert next(c for c in current if c["id"] == cid)["base_currency"] == "DKK"


def test_recompute_reports_what_it_did(client, seed):
    r = client.post(f"/api/v1/companies/{seed['comp_a']}/recompute-fx", headers=auth("tokA"))

    assert r.status_code == 200
    body = r.json()
    assert body["company_id"] == seed["comp_a"]
    assert body["base_currency"] == "DKK"
    assert body["converted"] + body["unconverted"] + body["unchanged"] == 3


def test_recompute_leaves_the_posted_amounts_alone(client, seed, engine):
    with Session(engine) as s:
        before = s.get(Invoice, seed["inv_a"])
        posted = (before.currency, before.total)

    client.post(f"/api/v1/companies/{seed['comp_a']}/recompute-fx", headers=auth("tokA"))

    with Session(engine) as s:
        after = s.get(Invoice, seed["inv_a"])
        assert (after.currency, after.total) == posted


@pytest.mark.parametrize("token", ["tok_memberA", "tok_viewerA"])
def test_recompute_needs_management_rights(client, seed, token):
    r = client.post(f"/api/v1/companies/{seed['comp_a']}/recompute-fx", headers=auth(token))
    assert r.status_code == 403


def test_recompute_of_a_foreign_company_is_404(client, seed):
    r = client.post(f"/api/v1/companies/{seed['comp_b']}/recompute-fx", headers=auth("tokA"))
    assert r.status_code == 404
