"""Company & organization management: authorization matrix, CRUD, cross-tenant."""
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from web_api.db.models import Organization, User

from .conftest import auth


def _create(client, token, **body):
    return client.post("/api/v1/companies", headers=auth(token), json={"name": "NewCo", **body})


# -- Authorization matrix (create) -------------------------------------------


@pytest.mark.parametrize("token", ["tokA", "tok_moderatorA", "tok_sysadmin"])
def test_managers_can_create_company(client, token):
    assert _create(client, token).status_code == 201


@pytest.mark.parametrize("token", ["tok_memberA", "tok_viewerA"])
def test_non_managers_cannot_create_company(client, token):
    assert _create(client, token).status_code == 403


# -- Create -------------------------------------------------------------------


def test_create_returns_company_under_callers_org(client):
    r = _create(client, "tokA", country_code="DK")
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "NewCo"
    assert body["country_code"] == "DK"
    assert body["is_active"] is True
    # It appears in the caller's company list
    names = [c["name"] for c in client.get("/api/v1/companies", headers=auth("tokA")).json()]
    assert "NewCo" in names


def test_create_requires_name(client):
    r = client.post("/api/v1/companies", headers=auth("tokA"), json={})
    assert r.status_code == 422


# -- Update -------------------------------------------------------------------


def test_update_company(client):
    cid = _create(client, "tok_moderatorA").json()["id"]
    r = client.patch(f"/api/v1/companies/{cid}", headers=auth("tok_moderatorA"),
                     json={"vat_number": "DK12345678"})
    assert r.status_code == 200
    assert r.json()["vat_number"] == "DK12345678"


def test_update_foreign_company_is_404(client, seed):
    # Org A admin cannot touch Org B's company
    r = client.patch(f"/api/v1/companies/{seed['comp_b']}", headers=auth("tokA"),
                     json={"name": "hijack"})
    assert r.status_code == 404


# -- Deactivate / activate + list filtering ----------------------------------


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


# -- System admin cross-org --------------------------------------------------


def test_system_admin_creates_company_in_another_org(client, seed):
    r = client.post("/api/v1/companies", headers=auth("tok_sysadmin"),
                    json={"name": "CrossOrgCo", "organization_id": seed["org_b"]})
    assert r.status_code == 201
    # It shows up for an Org B member
    names = [c["name"] for c in client.get("/api/v1/companies", headers=auth("tokB")).json()]
    assert "CrossOrgCo" in names


def test_non_admin_cannot_target_another_org(client, seed):
    # Org A admin is not a system admin: targeting Org B is refused
    r = client.post("/api/v1/companies", headers=auth("tokA"),
                    json={"name": "Nope", "organization_id": seed["org_b"]})
    assert r.status_code == 403


# -- Organization profile -----------------------------------------------------


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
    # Give Org B a slug, then Org A admin tries to claim the same one
    with Session(engine) as s:
        org_b = s.get(Organization, seed["org_b"])
        org_b.slug = "taken"
        s.add(org_b)
        s.commit()
    r = client.patch("/api/v1/organization", headers=auth("tokA"), json={"slug": "taken"})
    assert r.status_code == 409


# -- Provisioning of role / system-admin --------------------------------------


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
