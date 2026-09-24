"""Human verification of invoice-line categorization + audit history."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import Session, select

from web_api.db.models import AuditLog, Invoice, InvoiceLine, User

from web_api_testkit import auth


def _user_id(engine, clerk_user_id: str) -> str:
    """The internal User.id a Clerk principal was provisioned as (the audit actor)."""
    with Session(engine) as s:
        return s.exec(select(User).where(User.clerk_user_id == clerk_user_id)).one().id


# -- Authorization -----------------------------------------------------------


@pytest.mark.parametrize("token", ["tokA", "tok_moderatorA", "tok_sysadmin"])
def test_managers_can_verify(client, seed, token):
    r = client.post(f"/api/v1/invoice-lines/{seed['line_a1']}/verify", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["status"] == "verified"


@pytest.mark.parametrize("token", ["tok_memberA", "tok_viewerA"])
def test_non_managers_cannot_verify(client, engine, seed, token):
    r = client.post(f"/api/v1/invoice-lines/{seed['line_a1']}/verify", headers=auth(token))
    assert r.status_code == 403
    # The line is unchanged.
    with Session(engine) as s:
        assert s.get(InvoiceLine, seed["line_a1"]).status == "uncategorized"


def test_verify_foreign_line_is_404(client, seed):
    # Org A admin cannot verify Org B's line.
    r = client.post(f"/api/v1/invoice-lines/{seed['line_b1']}/verify", headers=auth("tokA"))
    assert r.status_code == 404


# -- Accept vs correct -------------------------------------------------------


def test_verify_accepts_ai_result_and_audits(client, engine, seed):
    r = client.post(f"/api/v1/invoice-lines/{seed['line_a2']}/verify", headers=auth("tokA"))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "verified"
    assert body["account_code"] == "6010"  # AI result preserved

    with Session(engine) as s:
        rows = s.exec(select(AuditLog).where(
            AuditLog.entity_type == "invoice_line",
            AuditLog.entity_id == seed["line_a2"])).all()
        assert len(rows) == 1
        assert rows[0].actor == _user_id(engine, "userA")  # attributed to the acting user
        assert rows[0].action == "verify"     # no correction → verify
        # Status change is captured in the diff.
        fields = {c["field"] for c in rows[0].changes}
        assert "status" in fields


def test_verify_with_correction_persists_and_records_edit(client, engine, seed):
    r = client.post(
        f"/api/v1/invoice-lines/{seed['line_a2']}/verify",
        headers=auth("tokA"),
        json={"level_2": "Professional Services", "account_code": "6610"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "verified"
    assert body["level_2"] == "Professional Services"
    assert body["account_code"] == "6610"

    with Session(engine) as s:
        row = s.exec(select(AuditLog).where(
            AuditLog.entity_id == seed["line_a2"])).one()
        assert row.action == "edit"           # correction → edit
        changed = {c["field"]: (c["old"], c["new"]) for c in row.changes}
        assert changed["account_code"] == ("6010", "6610")


# -- History accumulates & is tenant-scoped ----------------------------------


def test_audit_history_accumulates_in_order(client, engine, seed):
    # Seed a prior system row (explicitly earlier), then verify → two rows, oldest first.
    with Session(engine) as s:
        s.add(AuditLog(entity_type="invoice_line", entity_id=seed["line_a2"],
                       action="ai_categorize", actor="system", changes=[],
                       created_at=datetime(2020, 1, 1, tzinfo=timezone.utc)))
        s.commit()
    client.post(f"/api/v1/invoice-lines/{seed['line_a2']}/verify", headers=auth("tokA"))

    hist = client.get(f"/api/v1/invoice-lines/{seed['line_a2']}/audit", headers=auth("tokA")).json()
    assert [h["action"] for h in hist] == ["ai_categorize", "verify"]
    assert [h["actor"] for h in hist] == ["system", _user_id(engine, "userA")]


def test_audit_history_foreign_line_is_404(client, seed):
    r = client.get(f"/api/v1/invoice-lines/{seed['line_b1']}/audit", headers=auth("tokA"))
    assert r.status_code == 404


# -- Invoice rollup ----------------------------------------------------------


def test_invoice_rolls_up_to_verified_when_all_lines_verified(client, engine, seed):
    # inv_b has a single line; verifying it makes the invoice verified. Org B has
    # no manager token, so a system admin (cross-org) performs the verify.
    r = client.post(f"/api/v1/invoice-lines/{seed['line_b1']}/verify", headers=auth("tok_sysadmin"))
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.get(Invoice, seed["inv_b"]).status == "verified"


def test_invoice_stays_categorized_while_a_line_is_unverified(client, engine, seed):
    # inv_a has two lines; verifying only one leaves the invoice in-progress.
    client.post(f"/api/v1/invoice-lines/{seed['line_a2']}/verify", headers=auth("tokA"))
    with Session(engine) as s:
        assert s.get(Invoice, seed["inv_a"]).status == "categorized"
