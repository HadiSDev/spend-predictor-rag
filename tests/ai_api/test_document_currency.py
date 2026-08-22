"""Reconciling a document against a ledger that booked it in another currency.

Anthropic bills in EUR, Cloudflare in USD, EK Waterblocks in EUR — and all three
are posted to a Danish ledger in DKK. Reconciliation compared the document's own
figures against the ledger's total with no regard for that, so a perfectly read
EUR 62.11 credit memo was rejected for not summing to DKK 464.24. Those
documents could never be accepted no matter how well they were read.

The rule: **compare like with like, or say why you cannot.** The lines are
converted into the invoice's currency at the rate in force on the invoice's own
date — the same rule every other stored amount follows — and only then judged.
When no rate can be had, the extraction is rejected with a reason that names the
mismatch, rather than one claiming the arithmetic is wrong when it is not.

Converting is never silent about the risk: a rate is applied to a *sum*, so the
comparison is approximate by nature. That is why it feeds the tolerance check
and never a stored figure — `replace_invoice_lines` still writes the document's
own amounts, and `POST /companies/{id}/recompute-fx` remains the only path that
writes base figures.
"""
from __future__ import annotations

import pytest
from datetime import date
from decimal import Decimal

from ai_api.documents.currency import comparable_total, conversion_rate


class _Rates:
    """A stub rate source with the same shape as `FxService.get_rate`."""

    def __init__(self, table: dict[tuple[str, str], str] | None = None):
        self.table = table or {}
        self.asked: list[tuple] = []

    def get_rate(self, source, target, on_date):
        self.asked.append((source, target, on_date))
        # Mirrors the real contract: no date means no rate, since a rate is only
        # ever resolved against a publication day.
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
    """Most documents state one; assuming a mismatch where none is stated would
    reject every extraction that simply did not print a currency code."""
    fx = _Rates()

    total, reason = comparable_total(
        Decimal("58.00"), None, "DKK", date(2026, 6, 4), fx
    )

    assert total == Decimal("58.00")
    assert reason is None
    assert fx.asked == []


def test_a_foreign_currency_document_is_converted_before_it_is_judged():
    """The EK Waterblocks case: EUR 62.11 against a DKK 464.24 posting."""
    fx = _Rates({("EUR", "DKK"): "7.4736"})

    total, reason = comparable_total(
        Decimal("62.11"), "EUR", "DKK", date(2026, 6, 4), fx
    )

    assert reason is None
    assert total is not None
    assert abs(total - Decimal("464.19")) < Decimal("0.10")


def test_the_rate_is_taken_on_the_invoices_own_date():
    """Never today's rate — the same rule every stored amount already follows."""
    fx = _Rates({("USD", "DKK"): "6.44"})

    comparable_total(Decimal("10.46"), "USD", "DKK", date(2026, 5, 29), fx)

    assert fx.asked == [("USD", "DKK", date(2026, 5, 29))]


def test_a_mismatch_with_no_available_rate_is_refused_by_name():
    """Rejected for the reason that is true, not for arithmetic that is not."""
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
    """Nothing to convert *to*. Judged as posted, which is all we can do."""
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


# -- What counts as a stated currency ----------------------------------------


def test_a_currency_symbol_is_read_as_its_code():
    """A real reply gave `€` where the prompt asked for `EUR`. Comparing the two
    as strings declared a mismatch between a currency and itself, and refused a
    document that was already in the invoice's own currency."""
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
    """A real reply gave `US$`, which is one currency and not a dozen."""
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


@pytest.mark.parametrize("written", ["kr", "$", "Fr.", "shekels", "?"])
def test_a_currency_we_cannot_resolve_is_treated_as_unstated(written):
    """`kr` is DKK, NOK, SEK or ISK, and a bare `$` is a dozen currencies.

    Refusing the document would be worse than the behaviour that preceded any
    currency check — comparing at face value — and *guessing* a code is worse
    still, since it compares at a confidently wrong rate.
    """
    fx = _Rates({("USD", "DKK"): "6.44"})

    total, reason = comparable_total(
        Decimal("58.00"), written, "DKK", date(2026, 6, 4), fx
    )

    assert total == Decimal("58.00")
    assert reason is None
    assert fx.asked == []


# -- What gets stored, not just what gets compared ----------------------------


def test_the_rate_used_for_the_comparison_is_available_for_storage():
    """Comparing in one currency and storing in another is how a EUR 18.80 line
    ended up in a DKK column reading 18.80.

    The comparison was made currency-aware; storage was not, and
    `replace_invoice_lines` writes the document's own figure while
    `fx.convert_line` treats it as the invoice's currency. The rate has to leave
    this module for the writer to put the line in the invoice's money.
    """
    fx = _Rates({("EUR", "DKK"): "7.4736"})

    rate, reason = conversion_rate("EUR", "DKK", date(2026, 6, 4), fx)

    assert reason is None
    assert rate == Decimal("7.4736")


def test_a_same_currency_document_converts_at_one():
    """Not None — a rate of 1 multiplies harmlessly and needs no special case
    at the call site, which is where a forgotten None becomes a crash."""
    fx = _Rates()

    rate, reason = conversion_rate("DKK", "DKK", date(2026, 6, 4), fx)

    assert rate == Decimal("1") and reason is None
    assert fx.asked == []


def test_an_unstated_document_currency_converts_at_one():
    fx = _Rates()

    rate, reason = conversion_rate(None, "DKK", date(2026, 6, 4), fx)

    assert rate == Decimal("1") and reason is None


def test_no_rate_is_refused_rather_than_defaulted_to_one():
    """Defaulting to 1 is exactly the bug: it stores a foreign figure as local."""
    fx = _Rates()

    rate, reason = conversion_rate("EUR", "DKK", date(2026, 6, 4), fx)

    assert rate is None
    assert reason is not None and "EUR" in reason


def test_the_comparable_total_is_the_sum_scaled_by_that_rate():
    """One rate, one decision — the comparison and the stored lines must agree."""
    fx = _Rates({("EUR", "DKK"): "7.4736"})

    rate, _ = conversion_rate("EUR", "DKK", date(2026, 6, 4), fx)
    total, _ = comparable_total(Decimal("62.11"), "EUR", "DKK", date(2026, 6, 4), fx)

    assert total == Decimal("62.11") * rate
