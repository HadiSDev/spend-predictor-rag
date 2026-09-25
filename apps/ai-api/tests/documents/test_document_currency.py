"""Reconciling a document against a ledger that booked it in another currency."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from ai_api.documents.currency import comparable_total, conversion_rate


class _Rates:
    """A stub rate source with the same shape as `FxService.get_rate`."""

    def __init__(self, table: dict[tuple[str, str], str] | None = None):
        self.table = table or {}
        self.asked: list[tuple] = []

    def get_rate(self, source, target, on_date):
        self.asked.append((source, target, on_date))
        if on_date is None:
            return None
        rate = self.table.get((source, target))
        return (Decimal(rate), on_date) if rate else None


def test_a_document_in_the_ledgers_own_currency_is_not_converted():
    fx = _Rates()

    total, reason = comparable_total(
        Decimal("58.00"), "DKK", "DKK", date(2026, 6, 4), fx
    )

    assert total == Decimal("58.00")
    assert reason is None
    assert fx.asked == [], "a same-currency comparison needs no rate lookup"


def test_a_document_stating_no_currency_is_taken_at_face_value():
    fx = _Rates()

    total, reason = comparable_total(
        Decimal("58.00"), None, "DKK", date(2026, 6, 4), fx
    )

    assert total == Decimal("58.00")
    assert reason is None
    assert fx.asked == []


def test_a_foreign_currency_document_is_converted_before_it_is_judged():
    fx = _Rates({("EUR", "DKK"): "7.4736"})

    total, reason = comparable_total(
        Decimal("62.11"), "EUR", "DKK", date(2026, 6, 4), fx
    )

    assert reason is None
    assert total is not None
    assert abs(total - Decimal("464.19")) < Decimal("0.10")


def test_the_rate_is_taken_on_the_invoices_own_date():
    fx = _Rates({("USD", "DKK"): "6.44"})

    comparable_total(Decimal("10.46"), "USD", "DKK", date(2026, 5, 29), fx)

    assert fx.asked == [("USD", "DKK", date(2026, 5, 29))]


def test_a_mismatch_with_no_available_rate_is_refused_by_name():
    fx = _Rates()

    total, reason = comparable_total(
        Decimal("90.00"), "EUR", "DKK", date(2026, 6, 4), fx
    )

    assert total is None
    assert reason is not None
    assert "EUR" in reason and "DKK" in reason
    assert "rate" in reason.lower()


def test_the_currency_codes_are_compared_case_insensitively():
    fx = _Rates()

    total, reason = comparable_total(
        Decimal("58.00"), "dkk", "DKK", date(2026, 6, 4), fx
    )

    assert total == Decimal("58.00")
    assert reason is None


def test_an_invoice_with_no_currency_of_its_own_is_not_converted():
    fx = _Rates({("EUR", "DKK"): "7.4736"})

    total, reason = comparable_total(
        Decimal("62.11"), "EUR", None, date(2026, 6, 4), fx
    )

    assert total == Decimal("62.11")
    assert reason is None


def test_an_invoice_with_no_date_cannot_be_converted_and_says_so():
    fx = _Rates({("EUR", "DKK"): "7.4736"})

    total, reason = comparable_total(Decimal("62.11"), "EUR", "DKK", None, fx)

    assert total is None
    assert reason is not None and "EUR" in reason


def test_a_currency_symbol_is_read_as_its_code():
    fx = _Rates()

    total, reason = comparable_total(
        Decimal("90.30"), "€", "EUR", date(2026, 6, 1), fx
    )

    assert total == Decimal("90.30")
    assert reason is None
    assert fx.asked == [], "same currency, differently written, needs no rate"


def test_a_symbol_is_resolved_before_a_genuine_mismatch_is_declared():
    fx = _Rates({("EUR", "DKK"): "7.4736"})

    total, reason = comparable_total(
        Decimal("62.11"), "€", "DKK", date(2026, 6, 4), fx
    )

    assert reason is None
    assert fx.asked == [("EUR", "DKK", date(2026, 6, 4))]


def test_a_dollar_that_names_its_country_is_resolved():
    fx = _Rates({("USD", "DKK"): "6.44"})

    total, reason = comparable_total(
        Decimal("10.46"), "US$", "DKK", date(2026, 7, 9), fx
    )

    assert reason is None
    assert fx.asked == [("USD", "DKK", date(2026, 7, 9))]


@pytest.mark.parametrize("written", ["eur", " EUR ", "€", "EUR."])
def test_the_same_currency_written_any_way_is_not_a_mismatch(written):
    fx = _Rates()

    total, reason = comparable_total(
        Decimal("90.30"), written, "EUR", date(2026, 6, 1), fx
    )

    assert total == Decimal("90.30") and reason is None


@pytest.mark.parametrize("written", ["kr", "shekels", "?", "kroner"])
def test_a_currency_we_cannot_resolve_is_treated_as_unstated(written):
    fx = _Rates({("USD", "DKK"): "6.44"})

    total, reason = comparable_total(
        Decimal("58.00"), written, "DKK", date(2026, 6, 4), fx
    )

    assert total == Decimal("58.00")
    assert reason is None
    assert fx.asked == []


def test_the_rate_used_for_the_comparison_is_available_for_storage():
    fx = _Rates({("EUR", "DKK"): "7.4736"})

    rate, reason = conversion_rate("EUR", "DKK", date(2026, 6, 4), fx)

    assert reason is None
    assert rate == Decimal("7.4736")


def test_a_same_currency_document_converts_at_one():
    fx = _Rates()

    rate, reason = conversion_rate("DKK", "DKK", date(2026, 6, 4), fx)

    assert rate == Decimal("1") and reason is None
    assert fx.asked == []


def test_an_unstated_document_currency_converts_at_one():
    fx = _Rates()

    rate, reason = conversion_rate(None, "DKK", date(2026, 6, 4), fx)

    assert rate == Decimal("1") and reason is None


def test_no_rate_is_refused_rather_than_defaulted_to_one():
    fx = _Rates()

    rate, reason = conversion_rate("EUR", "DKK", date(2026, 6, 4), fx)

    assert rate is None
    assert reason is not None and "EUR" in reason


def test_the_comparable_total_is_the_sum_scaled_by_that_rate():
    fx = _Rates({("EUR", "DKK"): "7.4736"})

    rate, _ = conversion_rate("EUR", "DKK", date(2026, 6, 4), fx)
    total, _ = comparable_total(Decimal("62.11"), "EUR", "DKK", date(2026, 6, 4), fx)

    assert total == Decimal("62.11") * rate


@pytest.mark.parametrize(
    "written, code",
    [
        ("$", "USD"), ("US$", "USD"), ("CA$", "CAD"), ("A$", "AUD"),
        ("Fr.", "CHF"), ("zł", "PLN"), ("₹", "INR"), ("฿", "THB"),
        ("R$", "BRL"), ("₪", "ILS"), ("£", "GBP"), ("€", "EUR"),
    ],
)
def test_the_vendored_parser_resolves_the_symbols_it_knows(written, code):
    fx = _Rates({(code, "DKK"): "7"})

    rate, reason = conversion_rate(written, "DKK", date(2026, 6, 4), fx)

    assert reason is None
    assert fx.asked == [(code, "DKK", date(2026, 6, 4))]
