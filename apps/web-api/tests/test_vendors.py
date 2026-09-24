"""Vendor list: only the org's referenced suppliers, search, scoping."""
from __future__ import annotations

import pytest
from sqlmodel import Session

from web_api.db.models import Invoice, Vendor

from web_api_testkit import auth


@pytest.fixture
def seed_vendors(engine, seed):
    """Vendor X (Org A's inv_a), Vendor Y (Org B's inv_b), Vendor Z (unreferenced)."""
    with Session(engine) as s:
        vx = Vendor(name="Acme Supplies", country_code="DK", vat_number="DK111")
        vy = Vendor(name="Beta Legal", country_code="DK", vat_number="DK222")
        vz = Vendor(name="Zeta Unused", country_code="DK", vat_number="DK999")
        s.add(vx)
        s.add(vy)
        s.add(vz)
        s.commit()
        s.get(Invoice, seed["inv_a"]).vendor_id = vx.id
        s.get(Invoice, seed["inv_b"]).vendor_id = vy.id
        s.commit()
        return {"vx": vx.id, "vy": vy.id, "vz": vz.id}


def test_lists_only_orgs_referenced_vendors(client, seed_vendors):
    body = client.get("/api/v1/vendors", headers=auth("tokA")).json()
    ids = {v["id"] for v in body["items"]}
    assert ids == {seed_vendors["vx"]}          # not Org B's vendor, not the unused one
    assert body["items"][0]["name"] == "Acme Supplies"


def test_other_tenant_sees_its_own_vendor(client, seed_vendors):
    body = client.get("/api/v1/vendors", headers=auth("tokB")).json()
    assert {v["id"] for v in body["items"]} == {seed_vendors["vy"]}


def test_search_by_name_and_vat(client, seed_vendors):
    by_name = client.get("/api/v1/vendors", headers=auth("tokA"), params={"q": "acme"}).json()
    assert {v["id"] for v in by_name["items"]} == {seed_vendors["vx"]}
    none = client.get("/api/v1/vendors", headers=auth("tokA"), params={"q": "beta"}).json()
    assert none["items"] == []
    by_vat = client.get("/api/v1/vendors", headers=auth("tokA"), params={"q": "DK111"}).json()
    assert {v["id"] for v in by_vat["items"]} == {seed_vendors["vx"]}


def test_foreign_company_id_is_404(client, seed, seed_vendors):
    r = client.get("/api/v1/vendors", headers=auth("tokA"), params={"company_id": seed["comp_b"]})
    assert r.status_code == 404


def test_empty_scope_returns_empty(client, seed_vendors):
    body = client.get("/api/v1/vendors", headers=auth("tok_empty")).json()
    assert body == {"items": [], "page": 1, "page_size": 50, "total": 0}
