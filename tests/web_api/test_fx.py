"""FX service: rate resolution, caching, and per-row conversion.

Every test drives a `StubProvider`. Nothing here touches the network, and the
last test asserts that staying on the defaults keeps it that way.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from web_api.db.models import Company, ErpEntry, FxRate, Invoice, InvoiceLine, Organization
from web_api.fx import CONVERTED, UNCHANGED, UNCONVERTED, FxService, NullProvider, convert
from web_api.fx.provider import default_provider

# EUR-based reference rates, as the ECB publishes them.
FRIDAY = date(2026, 3, 6)
SATURDAY = date(2026, 3, 7)
RATES = {
    "EUR": Decimal("1"),
    "DKK": Decimal("7.4600"),
    "USD": Decimal("1.0850"),
    "SEK": Decimal("11.2000"),
}


class StubProvider:
    """Serves one publication date and records every call made to it."""

    def __init__(self, published: date = FRIDAY, rates: dict | None = None, fail: bool = False):
        self.published = published
        self.rates = RATES if rates is None else rates
        self.fail = fail
        self.calls: list[date] = []

    def fetch(self, rate_date: date):
        self.calls.append(rate_date)
        if self.fail:
            return None
        # Reference rates publish on business days: a weekend request is
        # answered with the preceding publication, as the real source does.
        return self.published, dict(self.rates)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def company(engine):
    with Session(engine) as s:
        org = Organization(name="FX Org", clerk_org_id="clerk_fx")
        s.add(org)
        s.commit()
        comp = Company(organization_id=org.id, name="FX Co", base_currency="DKK")
        s.add(comp)
        s.commit()
        return comp.id


# -- rate resolution ---------------------------------------------------------


def test_cross_rate_is_derived_from_two_eur_rates(session):
    fx = FxService(session, StubProvider())

    resolved = fx.get_rate("DKK", "SEK", FRIDAY)

    assert resolved is not None
    rate, published = resolved
    # 11.20 / 7.46, at the stored 8dp scale.
    assert rate == Decimal("1.50134048")
    assert published == FRIDAY


def test_cross_rate_needs_no_request_for_the_source_currency(session):
    provider = StubProvider()
    fx = FxService(session, provider)

    fx.get_rate("DKK", "SEK", FRIDAY)

    # One EUR-based fetch covers every pair for that date.
    assert provider.calls == [FRIDAY]


def test_same_currency_is_rate_one_on_its_own_date(session):
    provider = StubProvider()
    fx = FxService(session, provider)

    assert fx.get_rate("DKK", "DKK", SATURDAY) == (Decimal(1), SATURDAY)
    assert provider.calls == []


def test_weekend_resolves_back_to_the_previous_publication(session):
    fx = FxService(session, StubProvider(published=FRIDAY))

    resolved = fx.get_rate("USD", "DKK", SATURDAY)

    assert resolved is not None
    _, published = resolved
    assert published == FRIDAY


def test_weekend_is_cached_under_both_dates(session):
    fx = FxService(session, StubProvider(published=FRIDAY))
    fx.get_rate("USD", "DKK", SATURDAY)
    session.commit()

    saturday_rows = session.exec(select(FxRate).where(FxRate.rate_date == SATURDAY)).all()
    friday_rows = session.exec(select(FxRate).where(FxRate.rate_date == FRIDAY)).all()

    assert {r.quote_currency for r in saturday_rows} == set(RATES)
    assert {r.quote_currency for r in friday_rows} == set(RATES)
    # The Saturday rows remember which publication they really came from.
    assert {r.published_date for r in saturday_rows} == {FRIDAY}


def test_a_date_is_fetched_once_however_many_rows_need_it(session):
    provider = StubProvider()
    fx = FxService(session, provider)

    for _ in range(50):
        fx.get_rate("USD", "DKK", FRIDAY)

    assert provider.calls == [FRIDAY]


def test_a_second_service_reads_the_persisted_cache(session):
    first = StubProvider()
    FxService(session, first).get_rate("USD", "DKK", FRIDAY)
    session.commit()

    second = StubProvider()
    resolved = FxService(session, second).get_rate("USD", "DKK", FRIDAY)

    assert resolved is not None
    assert second.calls == []  # served entirely from `fx_rates`


def test_a_failing_provider_is_asked_only_once(session):
    provider = StubProvider(fail=True)
    fx = FxService(session, provider)

    for _ in range(10):
        assert fx.get_rate("USD", "DKK", FRIDAY) is None

    assert provider.calls == [FRIDAY]


@pytest.mark.parametrize(
    "source, target, on_date",
    [
        ("USD", "DKK", None),  # no transaction date
        (None, "DKK", FRIDAY),  # no posted currency
        ("kroner", "DKK", FRIDAY),  # not a currency code
        ("JPY", "DKK", FRIDAY),  # not published by the source
    ],
)
def test_a_rate_that_cannot_be_established_is_none(session, source, target, on_date):
    fx = FxService(session, StubProvider())

    assert fx.get_rate(source, target, on_date) is None


# -- conversion arithmetic ---------------------------------------------------


def test_convert_rounds_half_up_to_the_money_scale():
    assert convert(Decimal("10.00"), Decimal("1.50134048")) == Decimal("15.01")
    assert convert(Decimal("1.00"), Decimal("0.12500000")) == Decimal("0.13")
    assert convert(None, Decimal("1.5")) is None


# -- row conversion ----------------------------------------------------------


def test_an_invoice_is_converted_at_its_own_date(session, company):
    invoice = Invoice(company_id=company, currency="USD", invoice_date=FRIDAY,
                      total=Decimal("1000.00"), tax=Decimal("250.00"), status="uncategorized")
    session.add(invoice)
    fx = FxService(session, StubProvider())

    assert fx.convert_invoice(invoice, "DKK") == CONVERTED

    assert invoice.base_currency == "DKK"
    assert invoice.fx_rate_date == FRIDAY
    # 7.46 / 1.085
    assert invoice.fx_rate == Decimal("6.87557604")
    assert invoice.base_total == Decimal("6875.58")
    assert invoice.base_tax == Decimal("1718.89")


def test_a_stored_base_amount_is_reproducible_from_what_is_stored(session, company):
    invoice = Invoice(company_id=company, currency="USD", invoice_date=FRIDAY,
                      total=Decimal("1234.56"), status="uncategorized")
    session.add(invoice)
    FxService(session, StubProvider()).convert_invoice(invoice, "DKK")

    assert convert(invoice.total, invoice.fx_rate) == invoice.base_total


def test_the_posted_amount_is_never_rewritten(session, company):
    invoice = Invoice(company_id=company, currency="USD", invoice_date=FRIDAY,
                      total=Decimal("1000.00"), status="uncategorized")
    session.add(invoice)
    FxService(session, StubProvider()).convert_invoice(invoice, "DKK")

    assert invoice.currency == "USD"
    assert invoice.total == Decimal("1000.00")


def test_a_same_currency_row_still_counts_as_converted(session, company):
    invoice = Invoice(company_id=company, currency="DKK", invoice_date=FRIDAY,
                      total=Decimal("500.00"), status="uncategorized")
    session.add(invoice)

    assert FxService(session, StubProvider()).convert_invoice(invoice, "DKK") == CONVERTED

    assert invoice.fx_rate == Decimal(1)
    assert invoice.base_total == Decimal("500.00")
    assert invoice.base_currency == "DKK"


def test_debit_and_credit_convert_from_their_own_values(session, company):
    entry = ErpEntry(company_id=company, erp_account_id="acct", entry_type="expense",
                     accounting_date=FRIDAY, currency="USD",
                     debit_amount=Decimal("100.00"), credit_amount=Decimal("40.00"))
    session.add(entry)

    assert FxService(session, StubProvider()).convert_entry(entry, "DKK") == CONVERTED

    assert entry.base_debit_amount == Decimal("687.56")
    assert entry.base_credit_amount == Decimal("275.02")


def test_a_line_converts_at_its_invoices_date_and_currency(session, company):
    line = InvoiceLine(company_id=company, invoice_id="inv", amount=Decimal("200.00"),
                       status="uncategorized")
    session.add(line)
    fx = FxService(session, StubProvider())

    assert fx.convert_line(line, "DKK", currency="USD", invoice_date=FRIDAY) == CONVERTED

    assert line.base_amount == Decimal("1375.12")
    assert line.fx_rate_date == FRIDAY


def test_a_row_with_no_date_is_left_unconverted(session, company):
    invoice = Invoice(company_id=company, currency="USD", invoice_date=None,
                      total=Decimal("100.00"), status="uncategorized")
    session.add(invoice)

    assert FxService(session, StubProvider()).convert_invoice(invoice, "DKK") == UNCONVERTED

    assert invoice.base_total is None
    assert invoice.base_currency is None
    assert invoice.fx_rate is None
    assert invoice.total == Decimal("100.00")


def test_a_dead_provider_leaves_the_row_unconverted_not_half_converted(session, company):
    invoice = Invoice(company_id=company, currency="USD", invoice_date=FRIDAY,
                      total=Decimal("100.00"), tax=Decimal("25.00"), status="uncategorized")
    session.add(invoice)

    assert FxService(session, StubProvider(fail=True)).convert_invoice(invoice, "DKK") == UNCONVERTED

    assert (invoice.base_total, invoice.base_tax, invoice.fx_rate) == (None, None, None)


def test_an_already_converted_row_is_left_alone(session, company):
    invoice = Invoice(company_id=company, currency="USD", invoice_date=FRIDAY,
                      total=Decimal("100.00"), status="uncategorized")
    session.add(invoice)
    provider = StubProvider()
    FxService(session, provider).convert_invoice(invoice, "DKK")
    before = (invoice.base_total, invoice.fx_rate, invoice.fx_rate_date)

    second = StubProvider()
    assert FxService(session, second).convert_invoice(invoice, "DKK") == UNCHANGED

    assert (invoice.base_total, invoice.fx_rate, invoice.fx_rate_date) == before
    assert second.calls == []


def test_a_changed_base_currency_makes_a_row_convertible_again(session, company):
    invoice = Invoice(company_id=company, currency="USD", invoice_date=FRIDAY,
                      total=Decimal("100.00"), status="uncategorized")
    session.add(invoice)
    FxService(session, StubProvider()).convert_invoice(invoice, "DKK")

    assert FxService(session, StubProvider()).convert_invoice(invoice, "SEK") == CONVERTED

    assert invoice.base_currency == "SEK"
    assert invoice.fx_rate == Decimal("10.32258065")  # 11.20 / 1.085


# -- the default posture -----------------------------------------------------


def test_the_default_provider_makes_no_outbound_request(session, company):
    """FX is off unless switched on, so tests and offline runs stay hermetic."""
    assert isinstance(default_provider(), NullProvider)

    invoice = Invoice(company_id=company, currency="USD", invoice_date=FRIDAY,
                      total=Decimal("100.00"), status="uncategorized")
    session.add(invoice)

    assert FxService(session).convert_invoice(invoice, "DKK") == UNCONVERTED
