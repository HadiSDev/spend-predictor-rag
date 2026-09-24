"""Current-user endpoint + organization member directory."""
from __future__ import annotations

from .conftest import auth


# -- /users/me ---------------------------------------------------------------


def test_me_returns_caller_profile(client):
    body = client.get("/api/v1/users/me", headers=auth("tokA")).json()
    assert body["email"] == "a@a.com"
    assert body["name"] == "Alice"
    assert body["role"] == "admin"
    assert body["is_system_admin"] is False


def test_me_reflects_system_admin(client):
    body = client.get("/api/v1/users/me", headers=auth("tok_sysadmin")).json()
    assert body["is_system_admin"] is True


def test_me_without_token_is_401(client):
    assert client.get("/api/v1/users/me").status_code == 401


# -- /users (member directory) -----------------------------------------------


def test_users_lists_org_members_only(client):
    # Provision several Org A members and one Org B member by hitting /me.
    for tok in ("tokA", "tok_moderatorA", "tok_memberA", "tokB"):
        client.get("/api/v1/users/me", headers=auth(tok))

    body = client.get("/api/v1/users", headers=auth("tokA")).json()
    emails = {u["email"] for u in body["items"]}
    assert {"a@a.com", "mod@a.com", "mem@a.com"} <= emails
    assert "b@b.com" not in emails  # Org B member never leaks
    assert body["total"] == len(body["items"])


def test_users_is_tenant_scoped(client):
    for tok in ("tokA", "tokB"):
        client.get("/api/v1/users/me", headers=auth(tok))
    body = client.get("/api/v1/users", headers=auth("tokB")).json()
    assert {u["email"] for u in body["items"]} == {"b@b.com"}


def test_users_pagination(client):
    for tok in ("tokA", "tok_moderatorA", "tok_memberA"):
        client.get("/api/v1/users/me", headers=auth(tok))
    body = client.get("/api/v1/users", headers=auth("tokA"),
                      params={"page_size": 1, "page": 1}).json()
    assert body["page_size"] == 1 and len(body["items"]) == 1
    assert body["total"] >= 3
