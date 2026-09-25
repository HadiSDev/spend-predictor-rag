"""European number formatting, made unambiguous before a model reads it."""
from __future__ import annotations

import pytest

from ai_api.documents.numbers import normalize_numbers


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("986281 DJI Osmo Nano 128GB 1 919,20 0,00 1 1 919,20 25,00%",
         "986281 DJI Osmo Nano 128GB 1919.20 0.00 1 1919.20 25.00%"),
        ("Totalt ink. moms 2 399,00", "Totalt ink. moms 2399.00"),
        ("Total 1 234,56", "Total 1234.56"),
        ("1 234 567,89", "1234567.89"),
        ("Moms 25,00 %", "Moms 25.00 %"),
        ("919,20", "919.20"),
    ],
)
def test_european_amounts_become_unambiguous(raw, expected):
    assert normalize_numbers(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Total 1919.20 DKK",
        "Subtotal 1,919.20",
        "Dato / Tidspunkt 03.07.2026 19:54:38",
        "Ordrenummer 2125165980",
        "Elgiganten tilbyder 50, 30 eller 14 dages returret",
        "d8b0bb1d22ee49e996ac126f591",
    ],
)
def test_text_that_is_not_a_european_amount_is_left_alone(raw):
    assert normalize_numbers(raw) == raw


def test_a_quantity_beside_an_amount_stays_two_numbers():
    assert normalize_numbers("Rabat 0,00 Antal 1 1 919,20") == "Rabat 0.00 Antal 1 1919.20"


def test_normalization_is_idempotent():
    once = normalize_numbers("Totalt 2 399,00")
    assert normalize_numbers(once) == once
