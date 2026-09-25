"""Turning an amount as printed into a number, without guessing."""
from __future__ import annotations

import pytest

from ai_api.documents.numbers import normalize_numbers, parse_amount


@pytest.mark.parametrize(
    "printed, expected",
    [
        ("5.780,00", 5780.0),
        ("1.919,20", 1919.2),
        ("1.234.567,89", 1234567.89),
        ("1 919,20", 1919.2),
        ("1 234 567,89", 1234567.89),
        ("919,20", 919.2),
        ("58,00", 58.0),
        ("1919.20", 1919.2),
        ("1,919.20", 1919.2),
        ("58", 58.0),
        ("0", 0.0),
        ("DKK 5.780,00", 5780.0),
        ("kr. 58,00", 58.0),
        ("€90.30", 90.3),
        ("$10.46", 10.46),
        ("1 919,20 DKK", 1919.2),
        ("-58,00", -58.0),
        ("−58,00", -58.0),
        ("(58,00)", -58.0),
    ],
)
def test_an_unambiguous_amount_is_parsed(printed, expected):
    assert parse_amount(printed) == pytest.approx(expected)


@pytest.mark.parametrize(
    "printed",
    [
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
    assert parse_amount(58.0) == 58.0
    assert parse_amount(0) == 0.0


def test_a_long_digit_run_is_not_an_amount():
    assert parse_amount("3831109877204") is None


def test_dot_grouping_with_a_comma_decimal_is_normalized_in_text_too():
    assert normalize_numbers("Total 5.780,00 DKK") == "Total 5780.00 DKK"


def test_a_bare_dot_group_is_still_left_alone_in_text():
    assert normalize_numbers("Ordre 1.234") == "Ordre 1.234"
    assert normalize_numbers("Total 1919.20 DKK") == "Total 1919.20 DKK"


@pytest.mark.parametrize(
    "printed, expected",
    [
        ("5.780 kr.", 5780.0),
        ("5.780", 5780.0),
        ("1.234", 1234.0),
        ("1.234.567", 1234567.0),
        ("DKK 12.500", 12500.0),
        ("-1.500", -1500.0),
        ("1,234", 1234.0),
        ("1,234,567", 1234567.0),
    ],
)
def test_a_dot_group_of_three_is_thousands_when_the_figure_is_money(printed, expected):
    assert parse_amount(printed) == pytest.approx(expected)


@pytest.mark.parametrize(
    "printed, expected",
    [
        ("1.23", 1.23),
        ("1.2", 1.2),
        ("1919.20", 1919.2),
        ("5.780,50", 5780.5),
    ],
)
def test_a_short_dot_group_is_still_a_decimal(printed, expected):
    assert parse_amount(printed) == pytest.approx(expected)


def test_free_text_normalization_still_refuses_the_same_shape():
    assert normalize_numbers("Ordre 1.234") == "Ordre 1.234"
    assert normalize_numbers("Dato 03.07.2026") == "Dato 03.07.2026"
