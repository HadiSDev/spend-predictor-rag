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
        # 1234 in Copenhagen, 1.234 in London. Refused, never guessed.
        "1.234",
        "1,234",
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
