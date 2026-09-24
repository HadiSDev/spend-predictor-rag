"""Destroying a company, and the things a deletion must leave alone.

Companies are soft-deactivated by default and that stays the rule — this is the
one exception, for a company that should not exist. What the tests here are
really pinning is the *shape* of the exception: who may reach it, that nothing
happens until it is confirmed, that the purge leaves no residue, and that the
two catalogs which merely look company-owned survive it.

`Vendor` and `SpendTree` are the interesting cases. Both are reachable from a
company, neither belongs to it, and both would look like orphans to anyone
tidying up afterwards.
"""
from __future__ import annotations

from decimal import Decimal

from sqlmodel import Session, select

from web_api.db.models import (
    AuditLog,
    Company,
    ErpAccount,
    ErpCredential,
    ErpEntry,
    ErpIntegration,
    File,
    Invoice,
    InvoiceLine,
    Recommendation,
    SpendCategory,
    SpendCategorySuggestion,
    SpendTree,
    SyncState,
    Vendor,
)

from web_api_testkit import auth


def _delete(client, company_id: str, *, token: str = "tok_sysadmin", confirm: bool = False):
    suffix = "?confirm=true" if confirm else ""
    return client.delete(f"/api/v1/companies/{company_id}{suffix}", headers=auth(token))


def _count(engine, model, **where) -> int:
    with Session(engine) as s:
        rows = s.exec(select(model)).all()
    if not where:
        return len(rows)
    return len([r for r in rows if all(getattr(r, k) == v for k, v in where.items())])


# -- Who may do it -------------------------------------------------------------


def test_a_system_admin_may_delete(client, seed):
    assert _delete(client, seed["comp_a"], confirm=True).status_code == 200


def test_an_org_admin_may_not(client, seed, engine):
    """An org admin may deactivate — reversible, and theirs. Destroying a ledger
    is not something a support conversation can put right."""
    res = _delete(client, seed["comp_a"], token="tokA", confirm=True)

    assert res.status_code == 403
    with Session(engine) as s:
        assert s.get(Company, seed["comp_a"]) is not None


def test_a_moderator_member_or_viewer_may_not(client, seed, engine):
    for token in ("tok_moderatorA", "tok_memberA", "tok_viewerA"):
        res = _delete(client, seed["comp_a"], token=token, confirm=True)
        assert res.status_code == 403, token
    with Session(engine) as s:
        assert s.get(Company, seed["comp_a"]) is not None


def test_a_system_admin_reaches_another_organizations_company(client, seed):
    """System admins act across organizations, as they do everywhere else."""
    assert _delete(client, seed["comp_b"], confirm=True).status_code == 200


def test_an_unknown_company_is_404(client, seed):
    assert _delete(client, "no-such-company", confirm=True).status_code == 404


# -- The confirmation gate -----------------------------------------------------


def test_an_unconfirmed_deletion_is_refused_with_the_figures(client, seed, engine):
    res = _delete(client, seed["comp_a"])

    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["invoices"] == 1
    assert detail["lines"] == 2
    # Recognisable by its span, which is what a name cannot always do.
    assert detail["earliest"] == "2025-07-01"
    assert detail["latest"] == "2025-07-01"
    assert "cannot be undone" in detail["detail"]
    assert "eactivate" in detail["detail"], "the reversible option must be named"


def test_a_refusal_deletes_nothing(client, seed, engine):
    _delete(client, seed["comp_a"])

    with Session(engine) as s:
        assert s.get(Company, seed["comp_a"]) is not None
    assert _count(engine, Invoice, company_id=seed["comp_a"]) == 1
    assert _count(engine, InvoiceLine, company_id=seed["comp_a"]) == 2


def test_a_confirmed_deletion_proceeds(client, seed, engine):
    res = _delete(client, seed["comp_a"], confirm=True)

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == seed["comp_a"]
    assert body["invoices"] == 1 and body["lines"] == 2
    with Session(engine) as s:
        assert s.get(Company, seed["comp_a"]) is None


def test_an_empty_company_needs_no_confirmation(client, seed, engine):
    """Nothing to preview. A gate over zero only teaches the operator to click
    through the one that matters."""
    with Session(engine) as s:
        empty = Company(organization_id=seed["org_a"], name="Empty Co", base_currency="DKK")
        s.add(empty)
        s.commit()
        empty_id = empty.id

    res = _delete(client, empty_id)

    assert res.status_code == 200
    with Session(engine) as s:
        assert s.get(Company, empty_id) is None


# -- The purge leaves no residue ----------------------------------------------


def test_every_company_scoped_table_is_emptied(client, voucher_seed, engine):
    """Table by table on purpose: a table added later and not added to the purge
    has to fail *here*, rather than leave rows nobody can reach."""
    company_id = voucher_seed["comp_a"]

    assert _delete(client, company_id, confirm=True).status_code == 200

    assert _count(engine, Invoice, company_id=company_id) == 0
    assert _count(engine, InvoiceLine, company_id=company_id) == 0
    assert _count(engine, ErpEntry, company_id=company_id) == 0
    assert _count(engine, File, company_id=company_id) == 0
    assert _count(engine, Recommendation, company_id=company_id) == 0
    assert _count(engine, SpendCategorySuggestion, company_id=company_id) == 0
    assert _count(engine, ErpIntegration, company_id=company_id) == 0
    with Session(engine) as s:
        assert s.get(Company, company_id) is None
        # Reached only through the integration, so easy to forget.
        assert s.exec(select(ErpAccount)).all() == []
        assert s.exec(select(ErpCredential)).all() == []
        assert s.exec(select(SyncState)).all() == []


def test_audit_rows_for_the_destroyed_entities_go_too(client, seed, engine):
    """They carry no company id and no foreign key — the entity they name is
    their only tenancy anchor. Left behind, they could never again be attributed
    to anyone, filtered from an admin view, or answered for."""
    client.patch(
        f"/api/v1/invoice-lines/{seed['line_a1']}",
        json={"item_name": "Corrected"},
        headers=auth("tokA"),
    )
    assert _count(engine, AuditLog, entity_id=seed["line_a1"]) == 1

    _delete(client, seed["comp_a"], confirm=True)

    assert _count(engine, AuditLog, entity_id=seed["line_a1"]) == 0


def test_another_companys_audit_rows_are_untouched(client, seed, engine):
    """The purge selects by entity id, so it must not reach past its own.

    Written straight to the table rather than through the API: Org B's only
    principal is a `member`, so a PATCH would 403 and leave nothing to delete —
    the assertion would then pass against a purge that wiped every audit row in
    the database.
    """
    with Session(engine) as s:
        s.add(
            AuditLog(
                entity_type="invoice_line",
                entity_id=seed["line_b1"],
                action="edit",
                actor="userB",
                changes=[{"field": "item_name", "old": None, "new": "Kept"}],
            )
        )
        s.commit()
    assert _count(engine, AuditLog, entity_id=seed["line_b1"]) == 1

    _delete(client, seed["comp_a"], confirm=True)

    assert _count(engine, AuditLog, entity_id=seed["line_b1"]) == 1


def test_another_company_is_untouched(client, seed, engine):
    _delete(client, seed["comp_a"], confirm=True)

    with Session(engine) as s:
        assert s.get(Company, seed["comp_b"]) is not None
    assert _count(engine, Invoice, company_id=seed["comp_b"]) == 1
    assert _count(engine, InvoiceLine, company_id=seed["comp_b"]) == 1


# -- What survives on purpose --------------------------------------------------


def test_a_vendor_only_this_company_referenced_survives(client, seed, engine):
    """The catalog is global. A vendor nothing points at is not an orphan — it
    is a supplier nobody has bought from yet, which is where every vendor
    starts, and another organization may already be looking at it."""
    with Session(engine) as s:
        vendor = Vendor(name="Sole Supplier ApS")
        s.add(vendor)
        s.commit()
        vendor_id = vendor.id
        invoice = s.exec(
            select(Invoice).where(Invoice.company_id == seed["comp_a"])
        ).first()
        invoice.vendor_id = vendor_id
        s.add(invoice)
        s.commit()

    _delete(client, seed["comp_a"], confirm=True)

    with Session(engine) as s:
        assert s.get(Vendor, vendor_id) is not None


def test_a_shared_spend_tree_survives(client, seed, engine):
    """A tree belongs to the organization and several companies may share one —
    a bookkeeping firm running one taxonomy across its clients. Taking it with
    one of them would silently recategorize the rest."""
    with Session(engine) as s:
        tree = SpendTree(organization_id=seed["org_a"], name="Shared", max_depth=3)
        s.add(tree)
        s.commit()
        tree_id = tree.id
        node = SpendCategory(
            spend_tree_id=tree_id, parent_id=None, depth=1, name="Indirect",
            sort_order=0, level_1="Indirect",
        )
        s.add(node)
        first = s.get(Company, seed["comp_a"])
        first.spend_tree_id = tree_id
        second = Company(
            organization_id=seed["org_a"], name="Sibling", base_currency="DKK",
            spend_tree_id=tree_id,
        )
        s.add(first)
        s.add(second)
        s.commit()
        second_id = second.id

    _delete(client, seed["comp_a"], confirm=True)

    with Session(engine) as s:
        assert s.get(SpendTree, tree_id) is not None
        assert s.exec(select(SpendCategory)).all() != []
        assert s.get(Company, second_id).spend_tree_id == tree_id


def test_a_tree_left_assigned_to_nothing_survives(client, seed, engine):
    """Same reasoning with no sibling to protect: the tree is still the org's,
    and `DELETE /spend-trees/{id}` is how it goes if anyone wants it gone."""
    with Session(engine) as s:
        tree = SpendTree(organization_id=seed["org_a"], name="Lonely", max_depth=3)
        s.add(tree)
        s.commit()
        tree_id = tree.id
        company = s.get(Company, seed["comp_a"])
        company.spend_tree_id = tree_id
        s.add(company)
        s.commit()

    _delete(client, seed["comp_a"], confirm=True)

    with Session(engine) as s:
        assert s.get(SpendTree, tree_id) is not None


# -- Afterwards ----------------------------------------------------------------


def test_the_company_is_unreachable_not_hidden(client, seed):
    """The difference from deactivation, which deliberately keeps a company
    reachable by id so its history loads and it can be brought back."""
    _delete(client, seed["comp_a"], confirm=True)

    listed = client.get("/api/v1/companies?include_inactive=true", headers=auth("tokA")).json()
    assert seed["comp_a"] not in [c["id"] for c in listed]

    # Any route resolving a company by id no longer finds it.
    assert client.post(
        f"/api/v1/companies/{seed['comp_a']}/activate", headers=auth("tokA")
    ).status_code == 404


def test_its_spend_leaves_the_reports(client, seed, engine):
    before = client.get("/api/v1/reports/spend-by-vendor", headers=auth("tokA")).json()

    _delete(client, seed["comp_a"], confirm=True)

    after = client.get("/api/v1/reports/spend-by-vendor", headers=auth("tokA")).json()
    assert after != before or before["rows"] == []
    assert after["rows"] == [], "a deleted company's spend must not be counted"
