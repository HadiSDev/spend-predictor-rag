"""Vendored from groundley-ai/packages/parsers, unchanged except this note
and the import path.

Kept verbatim on purpose: these cases are the parser's specification, and
editing them to suit us would quietly move the contract we adopted it for.
"""
import pytest

import web_api.parsers.amount as parsers

valid_strict_amount_cases = [
    ("{2}1{0}111{0}111{1}11", 1111111.11),
    ("{2}111{0}111{1}11", 111111.11),
    ("{2}11{0}111{1}11", 11111.11),
    ("{2}1{0}111{1}11", 1111.11),
    ("{2}111{1}11", 111.11),
    ("{2}11{1}11", 11.11),
    ("{2}1{1}11", 1.11),
    ("{2}0{1}11", 0.11),
    ("{2}1111111{1}11", 1111111.11),
    ("{2}111111{1}11", 111111.11),
    ("{2}11111{1}11", 11111.11),
    ("{2}1111{1}11", 1111.11),
    ("{2}1111{1}11,-", 1111.11),
    ("{2}$1111{1}11", 1111.11),
    ("${2}1111{1}11", 1111.11),
]


@pytest.mark.parametrize("value, expected", valid_strict_amount_cases)
def test_parse_strict_amount_valid(value: str, expected: str):
    for c1, c2 in [(".", "."), (",", ","), (",", "."), (".", ","), (" ", "."), (" ", ",")]:
        assert expected == parsers.parse_strict_amount(value.format(c1, c2, "")), "Value: {}, Expected: {}".format(
            value.format(c1, c2, ""), expected
        )


@pytest.mark.parametrize("value, expected", valid_strict_amount_cases)
def test_parse_strict_amount_valid_string(value: str, expected: str):
    for c1, c2 in [(".", "."), (",", ","), (",", "."), (".", ","), (" ", "."), (" ", ",")]:
        assert str(expected) == parsers.parse_strict_amount(
            value.format(c1, c2, ""),
            as_string=True,
        ), "Value: {}, Expected: {}".format(value.format(c1, c2, ""), expected)


@pytest.mark.parametrize("value, expected", valid_strict_amount_cases)
def test_parse_strict_amount_absolute(value: str, expected: str):
    for c1, c2 in [(".", "."), (",", ","), (",", "."), (".", ","), (" ", "."), (" ", ",")]:
        assert expected == parsers.parse_strict_amount(value.format(c1, c2, "-"), as_absolute=True), (
            "Value: {}, Expected: {}".format(value.format(c1, c2, "-"), expected)
        )

    for c1, c2 in [(".", "."), (",", ","), (",", "."), (".", ","), (" ", "."), (" ", ",")]:
        assert -expected == parsers.parse_strict_amount(value.format(c1, c2, "-"), as_absolute=False), (
            "Value: {}, Expected: {}".format(value.format(c1, c2, "-"), -expected)
        )


invalid_strict_amount_cases = [
    # Too many/few digits
    "1.1111,00",
    "1.11,00",
    "00.11",
    # Dates
    "2019",
    "15/12/1995",
    "15-12-1995",
    "15.12.1995",
    "15/12/95",
    "15-12-95",
    "15.12.95",
    # Incomplete or wrong amounts
    "$15",
    "300, 10",
    "300. 10",
    "300,1",
    "300.1",
    "300",
    # Starting with 0
    "0.111.111,11",
    "011.111,11",
    "01.111,11",
    "0.111,11",
    "011,11",
    "01,11",
    "-0.111.111,11",
    "-011.111,11",
    "-01.111,11",
    "-0.111,11",
    "-011,11",
    "-01,11",
    # Other
    "Total:13,37",
    "Total: 13,37",
]


@pytest.mark.parametrize("value", invalid_strict_amount_cases)
def test_parse_strict_amount_invalid(value: str):
    assert parsers.parse_strict_amount(value) is None, "Value: {}, Expected: {}".format(value, "None")


def test_parse_amount():
    # non-noisy examples
    assert parsers.parse_amount("12.12") == 12.12
    assert parsers.parse_amount("12,12") == 12.12
    assert parsers.parse_amount("1,002.12") == 1002.12
    assert parsers.parse_amount("1.002,12") == 1002.12
    assert parsers.parse_amount("1.002.12") == 1002.12

    # typical decimal indicator
    assert parsers.parse_amount("12.-") == 12.0
    assert parsers.parse_amount("12,-") == 12.0

    # examples with -
    assert parsers.parse_amount("-1.00") == -1.0
    assert parsers.parse_amount("1.00-") == -1.0

    # dates with . delimiter do not parse as decimals
    assert parsers.parse_amount("20.04.02") is None

    # concatenated with text
    assert parsers.parse_amount("12.12dkr") == 12.12
    assert parsers.parse_amount("dkr12.12") == 12.12
    assert parsers.parse_amount("Total:12.12kr.") == 12.12

    # long non-separated amounts
    assert parsers.parse_amount("1.12") == 1.12
    assert parsers.parse_amount("12.12") == 12.12
    assert parsers.parse_amount("102.12") == 102.12
    assert parsers.parse_amount("1002.12") == 1002.12
    assert parsers.parse_amount("10002.12") == 10002.12

    # integers
    assert parsers.parse_amount("1") == 1.0
    assert parsers.parse_amount("12") == 12.0
    assert parsers.parse_amount("102") == 102.0
    assert parsers.parse_amount("1002") == 1002.0
    assert parsers.parse_amount("10002") == 10002.0

    # separated integers
    assert parsers.parse_amount("1.002") == 1002.0
    assert parsers.parse_amount("10.002") == 10002.0
    assert parsers.parse_amount("100.002") == 100002.0
    assert parsers.parse_amount("1.000.002") == 1000002.0

    # larger amounts
    assert parsers.parse_amount("467500,00") == 467500.0
    assert parsers.parse_amount("1260269") == 1260269.0
    assert parsers.parse_amount("606706,20") == 606706.2
    assert parsers.parse_amount("1639499.53") == 1639499.53

    # single digit after ./,
    assert parsers.parse_amount("1.1") == 1.1
    assert parsers.parse_amount("1,1") == 1.1

    # tricky stuff
    assert parsers.parse_amount(" ") is None

    # as string
    assert parsers.parse_amount("1", as_string=True) == "1.00"
    assert parsers.parse_amount("-1", as_string=True) == "-1.00"
    assert parsers.parse_amount("1.0", as_string=True) == "1.00"

    # valid cases with leading or trailing zeros
    assert parsers.parse_amount("0") == 0.0
    assert parsers.parse_amount("0.00") == 0.0
    assert parsers.parse_amount("0.0") == 0.0
    assert parsers.parse_amount("1.00") == 1.0

    # ignore whitespace
    assert parsers.parse_amount("1. 11") == 1.11
    assert parsers.parse_amount("  1. 11") == 1.11
    assert parsers.parse_amount("1. 11   ") == 1.11
    assert parsers.parse_amount("  1. 11   ") == 1.11

    # test as_absolute option
    assert parsers.parse_amount("-1.002.12") == -1002.12
    assert parsers.parse_amount("-1.002.12", as_absolute=True) == 1002.12
    assert parsers.parse_amount("-12,12") == -12.12
    assert parsers.parse_amount("-12,12", as_absolute=True) == 12.12


@pytest.mark.parametrize(
    "string",
    [
        "00 33 44",
        "00",
        "012345",
        "33 00 44",
        "00 33.44",
        "0000001234",
    ],
)
def test_parse_amount_invalid_special_cases(string: str):
    assert parsers.parse_amount(string) is None
