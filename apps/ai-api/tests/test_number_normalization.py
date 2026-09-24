"""European number formatting, made unambiguous before a model reads it.

A Danish invoice writes one thousand nine hundred nineteen and twenty øre as
`1 919,20` — space for thousands, comma for decimals. Beside a quantity column
that reads as quantity `1` and amount `919,20`, which is what the extractor
concluded on a real Elgiganten order confirmation: it returned 919.2 against a
line of 1919.20, and reconciliation correctly rejected the whole extraction.

Instructing the model not to do that is a hope. Normalizing the text is a fact,
and a pure function is testable in a way a prompt is not.
"""
from __future__ import annotations

import pytest

from ai_api.documents.numbers import normalize_numbers


@pytest.mark.parametrize(
    "raw, expected",
    [
        # The line that broke: space thousands + comma decimal.
        ("986281 DJI Osmo Nano 128GB 1 919,20 0,00 1 1 919,20 25,00%",
         "986281 DJI Osmo Nano 128GB 1919.20 0.00 1 1919.20 25.00%"),
        ("Totalt ink. moms 2 399,00", "Totalt ink. moms 2399.00"),
        # A non-breaking space is the same separator; PDFs emit both.
        ("Total 1 234,56", "Total 1234.56"),
        # Millions: more than one group.
        ("1 234 567,89", "1234567.89"),
        # A bare comma decimal, no thousands separator.
        ("Moms 25,00 %", "Moms 25.00 %"),
        ("919,20", "919.20"),
    ],
)
def test_european_amounts_become_unambiguous(raw, expected):
    assert normalize_numbers(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        # Already unambiguous: a dot decimal must survive untouched.
        "Total 1919.20 DKK",
        "Subtotal 1,919.20",           # US grouping — comma is the separator
        # A date is not an amount.
        "Dato / Tidspunkt 03.07.2026 19:54:38",
        "Ordrenummer 2125165980",
        # Prose containing a comma followed by a number.
        "Elgiganten tilbyder 50, 30 eller 14 dages returret",
        # An id that happens to have groups of three.
        "d8b0bb1d22ee49e996ac126f591",
    ],
)
def test_text_that_is_not_a_european_amount_is_left_alone(raw):
    assert normalize_numbers(raw) == raw


def test_a_quantity_beside_an_amount_stays_two_numbers():
    """The ambiguity itself: `1` then `1 919,20` must not merge into one."""
    assert normalize_numbers("Rabat 0,00 Antal 1 1 919,20") == "Rabat 0.00 Antal 1 1919.20"


def test_normalization_is_idempotent():
    once = normalize_numbers("Totalt 2 399,00")
    assert normalize_numbers(once) == once
