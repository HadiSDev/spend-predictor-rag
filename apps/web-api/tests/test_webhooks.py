"""Inbound Clerk webhook tests: signature, idempotency, and event handlers."""
from __future__ import annotations

import json

from sqlmodel import Session, select

from web_api.db.models import Company, File, Invoice, Organization, User, WebhookEvent

from web_api_testkit import auth, post_event, svix_headers


# -- Signature (7.1) ----------------------------------------------------------


def test_valid_signature_accepted(client):
    r = post_event(client, "organization.created", {"id": "org_new", "name": "New", "slug": "new"}, "m1")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_missing_headers_rejected(client):
    r = client.post("/api/v1/webhooks/clerk", content=json.dumps({"type": "organization.created", "data": {}}))
    assert r.status_code == 400


def test_tampered_body_rejected(client):
    payload = json.dumps({"type": "organization.created", "data": {"id": "x"}})
    headers = svix_headers(payload, "m2")
    r = client.post("/api/v1/webhooks/clerk", content=payload + " ", headers=headers)  # body changed post-sign
    assert r.status_code == 400


# -- Idempotency (7.2) --------------------------------------------------------


def test_idempotent_redelivery(client, engine):
    data = {"id": "org_dup", "name": "Dup", "slug": "dup"}
    r1 = post_event(client, "organization.created", data, "same-id")
    r2 = post_event(client, "organization.created", data, "same-id")
    assert r1.json()["status"] == "ok"
    assert r2.json()["status"] == "already_processed"
    with Session(engine) as s:
        assert len(s.exec(select(Organization).where(Organization.clerk_org_id == "org_dup")).all()) == 1
        events = s.exec(select(WebhookEvent).where(WebhookEvent.event_id == "same-id")).all()
        assert len(events) == 1 and events[0].processed is True


# -- Organization events (7.3) ------------------------------------------------


def test_org_created_provisions(client, engine):
    post_event(client, "organization.created", {"id": "org_c", "name": "Created Co", "slug": "created"}, "c1")
    with Session(engine) as s:
        org = s.exec(select(Organization).where(Organization.clerk_org_id == "org_c")).one()
        assert org.name == "Created Co" and org.slug == "created" and org.status == "active"


def test_org_updated_syncs_name_slug(client, engine, seed):
    post_event(client, "organization.updated", {"id": "clerk_orgA", "name": "Renamed A", "slug": "renamed-a"}, "u1")
    with Session(engine) as s:
        org = s.get(Organization, seed["org_a"])
        assert org.name == "Renamed A" and org.slug == "renamed-a"


def test_org_deleted_soft_suspends_and_retains_data(client, engine, seed):
    post_event(client, "organization.deleted", {"id": "clerk_orgA"}, "d1")
    with Session(engine) as s:
        org = s.get(Organization, seed["org_a"])
        assert org.status == "suspended" and org.suspended_at is not None
        assert s.get(Company, seed["comp_a"]) is not None
        assert s.get(Invoice, seed["inv_a"]) is not None


# -- Suspended access + reactivation (7.4) ------------------------------------


def test_suspended_blocks_access_and_reactivation_restores(client):
    assert client.get("/api/v1/companies", headers=auth("tokA")).status_code == 200
    post_event(client, "organization.deleted", {"id": "clerk_orgA"}, "s1")
    # Both read and management are blocked while suspended.
    assert client.get("/api/v1/companies", headers=auth("tokA")).status_code == 403
    assert client.post("/api/v1/companies", headers=auth("tokA"), json={"name": "X"}).status_code == 403
    post_event(client, "organization.created", {"id": "clerk_orgA", "name": "Org A", "slug": "a"}, "s2")
    assert client.get("/api/v1/companies", headers=auth("tokA")).status_code == 200


# -- Membership / user events (7.5) -------------------------------------------


def test_membership_created_then_role_updated(client, engine):
    mem = {"organization": {"id": "clerk_orgA", "name": "Org A", "slug": "a"}, "role": "org:member",
           "public_user_data": {"user_id": "user_new", "identifier": "new@a.com",
                                "first_name": "New", "last_name": "User"}}
    post_event(client, "organizationMembership.created", mem, "mc1")
    with Session(engine) as s:
        u = s.exec(select(User).where(User.clerk_user_id == "user_new")).one()
        assert u.role == "member" and u.email == "new@a.com" and u.name == "New User"
    post_event(client, "organizationMembership.updated", {**mem, "role": "org:moderator"}, "mu1")
    with Session(engine) as s:
        assert s.exec(select(User).where(User.clerk_user_id == "user_new")).one().role == "moderator"


def test_membership_deleted_revokes_user(client, engine):
    mem = {"organization": {"id": "clerk_orgA"}, "role": "org:member",
           "public_user_data": {"user_id": "user_rm", "identifier": "rm@a.com"}}
    post_event(client, "organizationMembership.created", mem, "rm1")
    post_event(client, "organizationMembership.deleted",
               {"organization": {"id": "clerk_orgA"}, "public_user_data": {"user_id": "user_rm"}}, "rm2")
    with Session(engine) as s:
        assert s.exec(select(User).where(User.clerk_user_id == "user_rm")).first() is None


def test_user_deleted_nulls_file_reference(client, engine, seed):
    mem = {"organization": {"id": "clerk_orgA"}, "role": "org:admin",
           "public_user_data": {"user_id": "user_file", "identifier": "f@a.com"}}
    post_event(client, "organizationMembership.created", mem, "uf1")
    with Session(engine) as s:
        u = s.exec(select(User).where(User.clerk_user_id == "user_file")).one()
        f = File(company_id=seed["comp_a"], uploaded_by=u.id, filename="x.pdf",
                 file_type="invoice_pdf", storage_path="/x")
        s.add(f)
        s.commit()
        fid = f.id
    post_event(client, "user.deleted", {"id": "user_file", "deleted": True}, "uf2")
    with Session(engine) as s:
        assert s.exec(select(User).where(User.clerk_user_id == "user_file")).first() is None
        f = s.get(File, fid)
        assert f is not None and f.uploaded_by is None  # integrity preserved


def test_user_updated_syncs_email_and_name(client, engine):
    mem = {"organization": {"id": "clerk_orgA"}, "role": "org:member",
           "public_user_data": {"user_id": "user_upd", "identifier": "old@a.com"}}
    post_event(client, "organizationMembership.created", mem, "uu1")
    post_event(client, "user.updated",
               {"id": "user_upd", "first_name": "Up", "last_name": "Dated",
                "email_addresses": [{"id": "e1", "email_address": "new@a.com"}],
                "primary_email_address_id": "e1"}, "uu2")
    with Session(engine) as s:
        u = s.exec(select(User).where(User.clerk_user_id == "user_upd")).one()
        assert u.email == "new@a.com" and u.name == "Up Dated"
