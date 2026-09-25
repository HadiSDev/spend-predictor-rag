"""Describing a supplier: once, only when asked, and never over a human."""
from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from ai_api.enrichment.vendors import (
    HUMAN,
    WEB,
    describe_vendors,
    vendors_needing_description,
)
from ai_api.sync import runner
from web_api.connectors.base import ErpVendorData
from web_api.db.models import Company, Invoice, Organization, Vendor


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _vendor(s: Session, name: str, **kwargs) -> Vendor:
    vendor = Vendor(name=name, **kwargs)
    s.add(vendor)
    s.commit()
    return vendor


def _describing(text: str):
    """A stub lookup that answers `text` and records who it was asked about."""
    asked: list[str] = []

    def describe(name: str, country_code: str | None) -> str:
        asked.append(name)
        return text

    describe.asked = asked  # type: ignore[attr-defined]
    return describe


def test_disabled_makes_no_request_and_writes_nothing(session):
    _vendor(session, "DSB")
    describe = _describing("Danish State Railways.")

    result = describe_vendors(session, enabled=False, describe=describe)

    assert describe.asked == []
    assert result.considered == 0
    assert session.exec(select(Vendor)).first().description is None


def test_a_supplier_is_described_and_stamped(session):
    _vendor(session, "DSB", country_code="DK")

    result = describe_vendors(
        session, enabled=True, describe=_describing("Danish State Railways."),
    )

    vendor = session.exec(select(Vendor)).first()
    assert vendor.description == "Danish State Railways."
    assert vendor.description_source == WEB
    assert result.described == 1


def test_a_supplier_is_researched_once(session):
    _vendor(session, "DSB")
    describe = _describing("Danish State Railways.")

    describe_vendors(session, enabled=True, describe=describe)
    describe_vendors(session, enabled=True, describe=describe)

    assert describe.asked == ["DSB"], "a described supplier must not be asked again"


def test_an_already_described_supplier_is_not_researched(session):
    _vendor(session, "DSB", description="Danish State Railways.")
    describe = _describing("Something else entirely.")

    result = describe_vendors(session, enabled=True, describe=describe)

    assert describe.asked == []
    assert result.considered == 0


def test_a_humans_description_is_never_overwritten(session):
    _vendor(session, "DSB", description="Rail operator, corrected by hand.",
            description_source=HUMAN)

    describe_vendors(session, enabled=True, describe=_describing("A model's guess."))

    vendor = session.exec(select(Vendor)).first()
    assert vendor.description == "Rail operator, corrected by hand."
    assert vendor.description_source == HUMAN


def test_a_description_written_during_the_lookup_survives(session):
    vendor = _vendor(session, "DSB")

    def describe(name: str, country_code: str | None) -> str:
        other = session.get(Vendor, vendor.id)
        other.description = "Rail operator, corrected by hand."
        other.description_source = HUMAN
        session.add(other)
        session.commit()
        return "A model's guess."

    result = describe_vendors(session, enabled=True, describe=describe)

    assert session.get(Vendor, vendor.id).description == "Rail operator, corrected by hand."
    assert session.get(Vendor, vendor.id).description_source == HUMAN
    assert result.described == 0 and result.skipped == 1


def test_a_failed_lookup_writes_nothing_and_raises_nothing(session):
    _vendor(session, "Obscure Holding ApS")

    def exploding(name: str, country_code: str | None) -> str:
        raise ConnectionError("connection refused")

    result = describe_vendors(session, enabled=True, describe=exploding)

    assert result.not_found == 1 and result.described == 0
    assert session.exec(select(Vendor)).first().description is None


def test_nothing_found_stores_nothing_rather_than_a_placeholder(session):
    _vendor(session, "Obscure Holding ApS")

    describe_vendors(session, enabled=True, describe=_describing(""))

    vendor = session.exec(select(Vendor)).first()
    assert vendor.description is None
    assert vendor.description_source is None


def test_a_company_filter_narrows_whose_backlog_is_worked(session):
    org = Organization(name="Org")
    session.add(org)
    session.commit()
    company = Company(organization_id=org.id, name="Acme", base_currency="DKK")
    session.add(company)
    session.commit()

    theirs = _vendor(session, "DSB")
    _vendor(session, "Unrelated ApS")
    session.add(Invoice(company_id=company.id, vendor_id=theirs.id, status="uncategorized"))
    session.commit()

    pending = vendors_needing_description(session, company_id=company.id)

    assert [v.name for v in pending] == ["DSB"]


def test_a_limit_paces_a_large_backlog(session):
    for name in ("A ApS", "B ApS", "C ApS"):
        _vendor(session, name)

    result = describe_vendors(
        session, enabled=True, limit=2, describe=_describing("A company."),
    )

    assert result.considered == 2


def test_a_sync_does_not_wipe_a_description_the_erp_never_stated(engine, make_tenant):
    make_tenant("Acme")
    runner.run_sync()

    with Session(engine) as s:
        vendor = s.exec(select(Vendor)).first()
        vendor.description = "Contoso sells cloud hosting."
        vendor.description_source = WEB
        s.add(vendor)
        s.commit()
        vendor_id = vendor.id

    runner.run_sync()

    with Session(engine) as s:
        assert s.get(Vendor, vendor_id).description == "Contoso sells cloud hosting."
        assert s.get(Vendor, vendor_id).description_source == WEB


def test_a_sync_may_state_a_description_the_erp_does_carry(
    engine, make_tenant, fake_connector, monkeypatch
):
    make_tenant("Acme")
    stated = [ErpVendorData(
        erp_id="V-1", name="Contoso ApS", country_code="DK", vat_number="DK99999999",
        description="Danish cloud hosting reseller.",
    )]
    monkeypatch.setattr(
        fake_connector, "fetch_vendors", lambda self, since=None: list(stated)
    )

    runner.run_sync()

    with Session(engine) as s:
        vendor = s.exec(select(Vendor)).first()
        assert vendor.description == "Danish cloud hosting reseller."
        assert vendor.description_source == "erp"


def test_a_sync_does_not_overwrite_a_humans_description(
    engine, make_tenant, fake_connector, monkeypatch
):
    make_tenant("Acme")
    runner.run_sync()

    with Session(engine) as s:
        vendor = s.exec(select(Vendor)).first()
        vendor.description = "Corrected by a person."
        vendor.description_source = HUMAN
        s.add(vendor)
        s.commit()
        vendor_id = vendor.id

    stated = [ErpVendorData(
        erp_id="V-1", name="Contoso ApS", country_code="DK", vat_number="DK99999999",
        description="The ERP's own guess.",
    )]
    monkeypatch.setattr(
        fake_connector, "fetch_vendors", lambda self, since=None: list(stated)
    )

    runner.run_sync()

    with Session(engine) as s:
        assert s.get(Vendor, vendor_id).description == "Corrected by a person."
