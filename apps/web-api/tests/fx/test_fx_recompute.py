"""Recomputing a company's stored base amounts."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from web_api.db.models import Company, ErpEntry, Invoice, InvoiceLine, Organization
from web_api.fx import CONVERTED, UNCHANGED, UNCONVERTED, FxService
from web_api.fx.recompute import recompute_company

MARCH = date(2026, 3, 6)
JUNE = date(2026, 6, 5)

RATES = {
    MARCH: {"EUR": Decimal("1"), "DKK": Decimal("7.4600"), "USD": Decimal("1.0850")},
    JUNE: {"EUR": Decimal("1"), "DKK": Decimal("7.4500"), "USD": Decimal("1.2000")},
}


class StubProvider:
    def __init__(self, rates=None):
        self.rates = RATES if rates is None else rates
        self.calls: list[date] = []

    def fetch(self, rate_date: date):
        self.calls.append(rate_date)
        published = self.rates.get(rate_date)
        return (rate_date, dict(published)) if published else None


@pytest.fixture
def company(engine):
    """A USD-invoicing company reporting in DKK, with data on two dates."""
    with Session(engine) as s:
        org = Organization(name="Recompute Org", clerk_org_id="clerk_recompute")
        s.add(org)
        s.commit()
        comp = Company(organization_id=org.id, name="Recompute Co", base_currency="DKK")
        s.add(comp)
        s.commit()

        march = Invoice(company_id=comp.id, currency="USD", invoice_date=MARCH,
                        total=Decimal("1000.00"), tax=Decimal("250.00"),
                        status="uncategorized")
        june = Invoice(company_id=comp.id, currency="USD", invoice_date=JUNE,
                       total=Decimal("1000.00"), status="uncategorized")
        s.add(march)
        s.add(june)
        s.commit()
        s.add(InvoiceLine(company_id=comp.id, invoice_id=march.id,
                          amount=Decimal("1000.00"), status="uncategorized"))
        s.add(ErpEntry(company_id=comp.id, erp_account_id="acct", entry_type="expense",
                       accounting_date=MARCH, currency="USD",
                       debit_amount=Decimal("100.00")))
        s.add(ErpEntry(company_id=comp.id, erp_account_id="acct", entry_type="payment",
                       accounting_date=None, currency="USD",
                       debit_amount=Decimal("50.00")))
        s.commit()
        return comp.id


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def test_recompute_converts_everything_convertible(session, company):
    counts = recompute_company(session, company, fx=FxService(session, StubProvider()))

    assert counts == {CONVERTED: 4, UNCONVERTED: 1, UNCHANGED: 0}


def test_each_row_is_converted_at_its_own_date(session, company):
    recompute_company(session, company, fx=FxService(session, StubProvider()))
    session.commit()

    invoices = {i.invoice_date: i for i in session.exec(select(Invoice)).all()}
    assert invoices[MARCH].fx_rate == Decimal("6.87557604")
    assert invoices[JUNE].fx_rate == Decimal("6.20833333")
    assert invoices[MARCH].base_total == Decimal("6875.58")
    assert invoices[JUNE].base_total == Decimal("6208.33")


def test_switching_base_currency_rewrites_the_stored_figures(session, company):
    recompute_company(session, company, fx=FxService(session, StubProvider()))
    session.commit()

    session.get(Company, company).base_currency = "EUR"
    counts = recompute_company(session, company, fx=FxService(session, StubProvider()))
    session.commit()

    assert counts[CONVERTED] == 4
    march = session.exec(select(Invoice).where(Invoice.invoice_date == MARCH)).one()
    assert march.base_currency == "EUR"
    assert march.fx_rate == Decimal("0.92165899")
    assert march.base_total == Decimal("921.66")


def test_the_posted_figures_are_byte_identical_afterwards(session, company):
    before = {
        i.id: (i.currency, i.total, i.tax)
        for i in session.exec(select(Invoice)).all()
    }
    entries_before = {
        e.id: (e.currency, e.debit_amount, e.credit_amount)
        for e in session.exec(select(ErpEntry)).all()
    }

    session.get(Company, company).base_currency = "SEK"
    recompute_company(session, company, fx=FxService(session, StubProvider()))
    session.commit()

    assert {i.id: (i.currency, i.total, i.tax)
            for i in session.exec(select(Invoice)).all()} == before
    assert {e.id: (e.currency, e.debit_amount, e.credit_amount)
            for e in session.exec(select(ErpEntry)).all()} == entries_before


def test_a_second_recompute_changes_nothing(session, company):
    recompute_company(session, company, fx=FxService(session, StubProvider()))
    session.commit()

    provider = StubProvider()
    counts = recompute_company(session, company, fx=FxService(session, provider))

    assert counts[UNCHANGED] == 4
    assert counts[CONVERTED] == 0
    assert provider.calls == []


def test_a_line_follows_its_invoice_not_its_own_clock(session, company):
    recompute_company(session, company, fx=FxService(session, StubProvider()))
    session.commit()

    line = session.exec(select(InvoiceLine)).one()
    invoice = session.get(Invoice, line.invoice_id)
    assert (line.fx_rate, line.fx_rate_date) == (invoice.fx_rate, invoice.fx_rate_date)


def test_recompute_fills_in_what_an_outage_left_behind(session, company):
    empty = recompute_company(session, company, fx=FxService(session, StubProvider(rates={})))
    session.commit()
    assert empty[UNCONVERTED] == 5

    counts = recompute_company(session, company, fx=FxService(session, StubProvider()))

    assert counts[CONVERTED] == 4


def test_an_unknown_company_is_an_error_not_a_silent_no_op(session):
    with pytest.raises(LookupError):
        recompute_company(session, "nope", fx=FxService(session, StubProvider()))
