"""Returning failed lines to the categorizer's queue."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session, select

from web_api.db.models import AuditLog, Company, Invoice, InvoiceLine

RECATEGORIZE_ACTION = "requeued_for_categorization"


def _url(company_id: str) -> str:
    return f"/api/v1/companies/{company_id}/recategorize"


@pytest.fixture
def failed_lines(engine, seed):
    """Org A's invoice gains one line per status, plus a stand-in failure."""
    ids = dict(seed)
    with Session(engine) as s:
        failed = InvoiceLine(
            company_id=ids["comp_a"], invoice_id=ids["inv_a"], description="Togbillet",
            amount=Decimal("11.00"), status="ai_failed", sequence=2, origin="erp",
            error_message="No spend category matched the description.",
            rationale="The invoice line only provides the supplier name and the amount.",
        )
        standin = InvoiceLine(
            company_id=ids["comp_a"], invoice_id=ids["inv_a"], description="",
            amount=Decimal("9.00"), status="ai_failed", sequence=3,
            origin="entry_fallback",
        )
        verified = InvoiceLine(
            company_id=ids["comp_a"], invoice_id=ids["inv_a"], description="Legal",
            amount=Decimal("5.00"), status="verified", sequence=4, origin="erp",
            level_1="Indirect", level_2="Professional Services", account_code="6610",
        )
        s.add(failed)
        s.add(standin)
        s.add(verified)
        s.commit()
        ids |= {"failed": failed.id, "standin": standin.id, "verified": verified.id}
    return ids


def _status_of(engine, line_id: str) -> str:
    with Session(engine) as s:
        return s.get(InvoiceLine, line_id).status


def test_failed_lines_are_queued(client, engine, failed_lines):
    response = client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    assert response.status_code == 200
    body = response.json()
    assert body["company_id"] == failed_lines["comp_a"]
    assert body["queued"] == 2
    assert _status_of(engine, failed_lines["failed"]) == "uncategorized"


def test_a_stand_in_failure_is_eligible(client, engine, failed_lines):
    client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    assert _status_of(engine, failed_lines["standin"]) == "uncategorized"


def test_a_verified_line_is_untouched(client, engine, failed_lines):
    client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    with Session(engine) as s:
        line = s.get(InvoiceLine, failed_lines["verified"])
        assert line.status == "verified"
        assert line.account_code == "6610"


def test_an_ai_categorized_line_is_untouched(client, engine, failed_lines):
    client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    with Session(engine) as s:
        line = s.get(InvoiceLine, failed_lines["line_a2"])
        assert line.status == "ai_categorized"
        assert line.account_code == "6010"


def test_an_already_uncategorized_line_is_not_counted(client, engine, failed_lines):
    response = client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    assert response.json()["queued"] == 2
    assert _status_of(engine, failed_lines["line_a1"]) == "uncategorized"


def test_nothing_to_queue_is_success(client, engine, seed):
    response = client.post(_url(seed["comp_a"]), headers={"Authorization": "Bearer tokA"})

    assert response.status_code == 200
    assert response.json()["queued"] == 0


def test_another_companys_lines_are_not_touched(client, engine, failed_lines):
    with Session(engine) as s:
        other = InvoiceLine(company_id=failed_lines["comp_b"], invoice_id=failed_lines["inv_b"],
                            description="x", amount=Decimal("1.00"), status="ai_failed")
        s.add(other)
        s.commit()
        other_id = other.id

    client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    assert _status_of(engine, other_id) == "ai_failed"


@pytest.mark.parametrize("token", ["tokA", "tok_moderatorA", "tok_sysadmin"])
def test_management_roles_may_queue(client, failed_lines, token):
    response = client.post(_url(failed_lines["comp_a"]), headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200


@pytest.mark.parametrize("token", ["tok_memberA", "tok_viewerA"])
def test_read_only_roles_may_not_queue(client, engine, failed_lines, token):
    response = client.post(_url(failed_lines["comp_a"]), headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert _status_of(engine, failed_lines["failed"]) == "ai_failed"


def test_another_organizations_company_is_404(client, engine, failed_lines):
    with Session(engine) as s:
        foreign = InvoiceLine(company_id=failed_lines["comp_b"], invoice_id=failed_lines["inv_b"],
                              description="x", amount=Decimal("1.00"), status="ai_failed")
        s.add(foreign)
        s.commit()
        foreign_id = foreign.id

    response = client.post(_url(failed_lines["comp_b"]), headers={"Authorization": "Bearer tokA"})

    assert response.status_code == 404
    assert _status_of(engine, foreign_id) == "ai_failed"


def test_a_deactivated_company_can_still_be_queued(client, engine, failed_lines):
    with Session(engine) as s:
        company = s.get(Company, failed_lines["comp_a"])
        company.is_active = False
        s.add(company)
        s.commit()

    response = client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    assert response.status_code == 200
    assert response.json()["queued"] == 2


def test_the_stale_failure_message_is_cleared(client, engine, failed_lines):
    client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    with Session(engine) as s:
        assert s.get(InvoiceLine, failed_lines["failed"]).error_message is None


def test_the_stale_rationale_is_cleared(client, engine, failed_lines):
    client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    with Session(engine) as s:
        assert s.get(InvoiceLine, failed_lines["failed"]).rationale is None


def test_clearing_the_rationale_is_audited(client, engine, failed_lines):
    client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    with Session(engine) as s:
        row = s.exec(
            select(AuditLog).where(
                AuditLog.entity_id == failed_lines["failed"],
                AuditLog.action == RECATEGORIZE_ACTION,
            )
        ).first()
        fields = {c["field"]: c for c in row.changes}
        assert fields["rationale"]["old"].startswith("The invoice line only provides")
        assert fields["rationale"]["new"] is None


def test_each_reset_is_audited(client, engine, failed_lines):
    client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    with Session(engine) as s:
        row = s.exec(
            select(AuditLog).where(
                AuditLog.entity_id == failed_lines["failed"],
                AuditLog.action == RECATEGORIZE_ACTION,
            )
        ).one()
        assert row.entity_type == "invoice_line"
        assert row.actor == "system"
        change = next(c for c in row.changes if c["field"] == "status")
        assert change["old"] == "ai_failed"
        assert change["new"] == "uncategorized"


def test_untouched_lines_get_no_audit_row(client, engine, failed_lines):
    client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    with Session(engine) as s:
        rows = s.exec(
            select(AuditLog).where(AuditLog.action == RECATEGORIZE_ACTION)
        ).all()
        assert {r.entity_id for r in rows} == {failed_lines["failed"], failed_lines["standin"]}


def test_the_invoice_rollup_follows(client, engine, seed):
    with Session(engine) as s:
        for line_id in (seed["line_a1"], seed["line_a2"]):
            line = s.get(InvoiceLine, line_id)
            line.status = "ai_failed"
            s.add(line)
        invoice = s.get(Invoice, seed["inv_a"])
        invoice.status = "categorized"
        s.add(invoice)
        s.commit()

    client.post(_url(seed["comp_a"]), headers={"Authorization": "Bearer tokA"})

    with Session(engine) as s:
        assert s.get(Invoice, seed["inv_a"]).status == "uncategorized"


def test_the_endpoint_categorizes_nothing(client, engine, failed_lines):
    client.post(_url(failed_lines["comp_a"]), headers={"Authorization": "Bearer tokA"})

    with Session(engine) as s:
        line = s.get(InvoiceLine, failed_lines["failed"])
        assert line.spend_category_id is None
        assert line.level_1 is None
        assert line.account_code is None
