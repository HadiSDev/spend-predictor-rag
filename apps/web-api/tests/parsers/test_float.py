"""Tests for the vendored float parser."""
import pytest

import web_api.parsers.float as parsers

separator_insensitive_floats = [
    ("1{0}111{1}11", 1111.11),
    ("1{0}111{0}111{1}11", 1111111.11),
    ("1{0}111{1}1111", 1111.1111),
    ("1{0}111{0}111{1}1111", 1111111.1111),
    ("1{0}111{1}111,-", 1111111.0),
]


@pytest.mark.parametrize("value, expected", separator_insensitive_floats)
def test_parse_separator_insensitive_float(value, expected):
    for c1, c2 in [(".", "."), (",", ","), (",", "."), (".", ","), (" ", "."), (" ", ",")]:
        assert expected == parsers.parse_float(value.format(c1, c2)), "Value: {}, Expected: {}".format(
            value.format(c1, c2), expected
        )


separator_sensitive_floats = [
    ("1{0}111{1}111", 1111.111, 1111111.0),
    ("1{0}111{0}111{1}111", 1111111.111, 1111111111.0),
]


@pytest.mark.parametrize("value, expected, expected_same_separator", separator_sensitive_floats)
def test_parse_separator_sensitive_float(value, expected, expected_same_separator):
    for c1, c2 in [(",", "."), (".", ","), (" ", "."), (" ", ",")]:
        assert expected == parsers.parse_float(value.format(c1, c2)), "Value: {}, Expected: {}".format(
            value.format(c1, c2), expected
        )

    for c1, c2 in [(".", "."), (",", ",")]:
        assert expected_same_separator == parsers.parse_float(value.format(c1, c2)), "Value: {}, Expected: {}".format(
            value.format(c1, c2), expected_same_separator
        )


invalid_cases = [
    "1.1111,00",
    "1.11,00",
    "00.11",
    "15/12/1995",
    "15-12-1995",
    "15.12.1995",
    "15/12/95",
    "15-12-95",
    "15.12.95",
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
]


@pytest.mark.parametrize("value", invalid_cases)
def test_parse_float_invalid(value):
    assert parsers.parse_float(value) is None, "Value: {}, Expected: {}".format(value, "None")


special_cases = [
    ("12.123", 12.123, {}),
    ("12,123", 12.123, {}),
    ("1,002.120", 1002.12, {}),
    ("1.002,123", 1002.123, {}),
    ("1.002.123", 1002123, {}),
    ("12.-", 12.0, {}),
    ("12,-", 12.0, {}),
    ("-1.001", -1.001, {}),
    ("1.001-", -1.001, {}),
    ("(1.00)", -1.0, {}),
    ("(1.002.12)", -1002.12, {}),
    ("(1.00)", -1.0, {}),
    ("(1.002.12)", -1002.12, {}),
    ("20.04.02", None, {}),
    ("12.12dkr", 12.12, {}),
    ("dkr12.12", 12.12, {}),
    ("Total:12.123kr.", 12.123, {}),
    ("1.12", 1.12, {}),
    ("12.12", 12.12, {}),
    ("102.12", 102.12, {}),
    ("1002.123", 1002.123, {}),
    ("10002.1234", 10002.1234, {}),
    ("1", 1.0, {}),
    ("12", 12.0, {}),
    ("102", 102.0, {}),
    ("1002", 1002.0, {}),
    ("10002", 10002.0, {}),
    ("1.000.002", 1000002.0, {}),
    ("467500,00", 467500.0, {}),
    ("1260269", 1260269.0, {}),
    ("606706,20", 606706.2, {}),
    ("1639499.531", 1639499.531, {}),
    ("1.1", 1.1, {}),
    ("1,1", 1.1, {}),
    (" ", None, {}),
    ("1", "1.0", {"as_string": True}),
    ("-1", "-1.0", {"as_string": True}),
    ("1.001", "1.001", {"as_string": True}),
    ("0", 0.0, {}),
    ("0.00", 0.0, {}),
    ("0.0", 0.0, {}),
    ("1.00", 1.0, {}),
    ("1. 11", 1.11, {}),
    ("  1. 113", 1.113, {}),
    ("-1002.12", -1002.12, {}),
    ("-1002.12", 1002.12, {"as_absolute": True}),
    ("-12,12", -12.12, {}),
    ("-12,12", 12.12, {"as_absolute": True}),
    ("4321365 -cruft", -4321365.0, {}),
]


@pytest.mark.parametrize("value, expected, kwargs", special_cases)
def test_parse_float_special_cases(value, expected, kwargs):
    assert expected == parsers.parse_float(value, **kwargs), "Value: {}, Expected: {}".format(value, expected)


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
def test_parse_float_invalid_special_cases(string):
    assert parsers.parse_float(string) is None
