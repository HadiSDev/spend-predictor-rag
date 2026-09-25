"""Outbound org sync: DELETE /organization propagation, gating, loop prevention."""
from __future__ import annotations

from sqlmodel import Session

from web_api.auth.clerk_client import ClerkClient
from web_api.db.models import Organization

from web_api_testkit import auth
from web_api_testkit import post_event


def test_delete_org_requires_org_admin(client):
    for token in ("tok_moderatorA", "tok_memberA", "tok_viewerA"):
        assert client.delete("/api/v1/organization", headers=auth(token)).status_code == 403


def test_admin_delete_suspends_and_propagates(client, engine, seed, clerk_recorder):
    r = client.delete("/api/v1/organization", headers=auth("tokA"))
    assert r.status_code == 200
    assert r.json()["status"] == "suspended"
    with Session(engine) as s:
        org = s.get(Organization, seed["org_a"])
        assert org.status == "suspended" and org.suspended_at is not None
    assert clerk_recorder.deleted == ["clerk_orgA"]


def test_echoed_deletion_is_noop(client, engine, seed, clerk_recorder):
    client.delete("/api/v1/organization", headers=auth("tokA"))
    with Session(engine) as s:
        before = s.get(Organization, seed["org_a"]).suspended_at
    r = post_event(client, "organization.deleted", {"id": "clerk_orgA"}, "echo-1")
    assert r.status_code == 200
    with Session(engine) as s:
        org = s.get(Organization, seed["org_a"])
        assert org.status == "suspended" and org.suspended_at == before


def test_client_disabled_makes_no_call():
    c = ClerkClient(secret_key="sk_test", base_url="https://api.clerk.com/v1", disabled=True)
    assert c.enabled is False
    assert c.delete_organization("org_x") is False


def test_client_without_secret_makes_no_call():
    c = ClerkClient(secret_key="", base_url="https://api.clerk.com/v1", disabled=False)
    assert c.enabled is False
    assert c.delete_organization("org_x") is False


def test_client_skips_when_no_clerk_org_id():
    c = ClerkClient(secret_key="sk_test", base_url="https://api.clerk.com/v1", disabled=False)
    assert c.enabled is True
    assert c.delete_organization("") is False
