"""Turning an amount as printed into a number, without guessing.

The vision path cannot rewrite a document before the model reads it — pixels are
not text — so the ambiguity that :mod:`ai_api.documents.numbers` removes from a
text layer has to be handled on the way *back* instead. The model transcribes an
amount exactly as printed and this parses it, which puts the decision in code
that can be tested rather than in a prompt that can only be hoped at.

It earns its place on real failures: a Danish DSB receipt printing `5.780,00`
came back from the model as `5.78`, and an EKWB invoice came back with the
product's barcode where its amount should be.

The one rule that matters: **an amount whose separator is genuinely ambiguous is
refused, not guessed.** `1.234` is 1234 in Copenhagen and 1.234 in London, and a
parser that picks one is wrong roughly half the time on a mixed ledger — silently,
in a figure that flows straight into a spend report.
"""
from __future__ import annotations

import pytest

from ai_api.documents.numbers import normalize_numbers, parse_amount


@pytest.mark.parametrize(
    "printed, expected",
    [
        # Unambiguous European: dot groups AND a comma decimal.
        ("5.780,00", 5780.0),
        ("1.919,20", 1919.2),
        ("1.234.567,89", 1234567.89),
        # Unambiguous European: space groups and a comma decimal.
        ("1 919,20", 1919.2),
        ("1 234 567,89", 1234567.89),
        # A bare comma decimal.
        ("919,20", 919.2),
        ("58,00", 58.0),
        # Plain and US forms.
        ("1919.20", 1919.2),
        ("1,919.20", 1919.2),
        ("58", 58.0),
        ("0", 0.0),
        # Currency symbols and codes travel with the figure.
        ("DKK 5.780,00", 5780.0),
        ("kr. 58,00", 58.0),
        ("€90.30", 90.3),
        ("$10.46", 10.46),
        ("1 919,20 DKK", 1919.2),
        # Negative amounts: a credit line is real.
        ("-58,00", -58.0),
        ("−58,00", -58.0),  # U+2212 minus, which PDFs emit
        ("(58,00)", -58.0),  # accounting parentheses
    ],
)
def test_an_unambiguous_amount_is_parsed(printed, expected):
    assert parse_amount(printed) == pytest.approx(expected)


@pytest.mark.parametrize(
    "printed",
    [
        # Not an amount at all: the EKWB barcode that arrived as a line total.
        "3831109813256",
        "",
        "   ",
        None,
        "n/a",
        "null",
        "—",
    ],
)
def test_an_amount_we_cannot_read_is_refused_rather_than_guessed(printed):
    assert parse_amount(printed) is None


def test_a_number_that_is_already_a_number_passes_through():
    """The model sometimes obeys the schema and sends a float. That is fine."""
    assert parse_amount(58.0) == 58.0
    assert parse_amount(0) == 0.0


def test_a_long_digit_run_is_not_an_amount():
    """A 13-digit EAN has no decimal point and no plausible reading as money."""
    assert parse_amount("3831109877204") is None


# -- The shared normalizer gained the dot-grouped form ------------------------


def test_dot_grouping_with_a_comma_decimal_is_normalized_in_text_too():
    """`5.780,00` is unambiguous, and the text path should not have to guess."""
    assert normalize_numbers("Total 5.780,00 DKK") == "Total 5780.00 DKK"


def test_a_bare_dot_group_is_still_left_alone_in_text():
    """No comma decimal means no evidence the text is European. Hands off."""
    assert normalize_numbers("Ordre 1.234") == "Ordre 1.234"
    assert normalize_numbers("Total 1919.20 DKK") == "Total 1919.20 DKK"


# -- Dot grouping, for money specifically ------------------------------------


@pytest.mark.parametrize(
    "printed, expected",
    [
        # The DSB receipt: `5.780 kr.` is 5780 kroner, and the ledger agrees.
        ("5.780 kr.", 5780.0),
        ("5.780", 5780.0),
        ("1.234", 1234.0),
        ("1.234.567", 1234567.0),
        ("DKK 12.500", 12500.0),
        ("-1.500", -1500.0),
        # A comma group reads the same way, for the same reason: as money, the
        # only alternative is three decimal places, which no ordinary currency
        # has.
        ("1,234", 1234.0),
        ("1,234,567", 1234567.0),
    ],
)
def test_a_dot_group_of_three_is_thousands_when_the_figure_is_money(printed, expected):
    """`1.234` is genuinely ambiguous in free text and this module refuses it
    there — but not here.

    An amount is not free text. No ordinary currency carries three decimal
    places, so three digits after a lone dot can only be a thousands group. A
    real DSB receipt priced `5.780 kr.` against a DKK 5780.00 posting was
    refused on the general rule and cost us the document, while the ledger sat
    beside it stating the answer.

    The trade-off, accepted: a three-decimal currency (KWD, BHD, TND) would be
    misread by a factor of a thousand. None appears in this ledger, and the
    alternative is refusing every Danish and German amount printed this way.
    """
    assert parse_amount(printed) == pytest.approx(expected)


@pytest.mark.parametrize(
    "printed, expected",
    [
        # One or two digits after the dot is a decimal, not a group.
        ("1.23", 1.23),
        ("1.2", 1.2),
        ("1919.20", 1919.2),
        # A comma decimal still wins outright when both are present.
        ("5.780,50", 5780.5),
    ],
)
def test_a_short_dot_group_is_still_a_decimal(printed, expected):
    assert parse_amount(printed) == pytest.approx(expected)


def test_free_text_normalization_still_refuses_the_same_shape():
    """The relaxation is `parse_amount`'s alone. In a text layer, `1.234` may be
    a quantity, an order reference or a version, and rewriting it would corrupt
    all three."""
    assert normalize_numbers("Ordre 1.234") == "Ordre 1.234"
    assert normalize_numbers("Dato 03.07.2026") == "Dato 03.07.2026"
