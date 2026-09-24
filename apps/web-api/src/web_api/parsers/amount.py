"""Vendored from `groundley-ai/packages/parsers`, unchanged.

Adopted rather than reimplemented after a hand-rolled parser in this repo kept
getting real invoices wrong: `5.780 kr.` refused as ambiguous when the ledger
beside it said 5780, `31.12.99` at risk of reading as 31.12, and a 13-digit
EKWB article number accepted as a line total. This one analyses a figure's
groups and separators instead of matching a handful of shapes.

**Kept verbatim.** Local needs are handled by the callers that wrap it —
`ai_api/documents/numbers.py` normalizes a U+2212 minus before calling, because
that is our documents' quirk and not this parser's business. Editing the file
would fork it from upstream and make the next update a merge.
"""
import re
from typing import Union

import regex

re_amount_non_digit = re.compile(r"^[^\d-]+|[^\d-]+$")
re_amount_trailing_space_after_comma = re.compile(r"([,.])\s+")
re_amount_comma_space = re.compile(r",|\s")
re_amount_dotdash = re.compile(r"\.-")
re_amount_invalid = re.compile(r"^0\d+")
re_amount_strict = r"^\d{1,3}(\.\d{3})*(\.\d\d)?$"  # eg. 1.000.000.00
re_amount_sloppy = r"^\d{1,7}(\.\d?\d)?$"
re_amount_format = re.compile("|".join([re_amount_strict, re_amount_sloppy]))


def format_amount(float_amount: float):
    if float_amount is not None:
        return f"{float_amount:.2f}"
    return None


def normalize_amount(value: Union[str, float]):
    if isinstance(value, float):
        # format the value to .2f even if we return float
        value = format_amount(value)
        return value
    return value


def normalize_parse_amount(value: Union[str, float], as_string: bool = False, as_absolute: bool = False):
    return parse_amount(string=normalize_amount(value), as_string=as_string, as_absolute=as_absolute)


def parse_amount(string: str, as_string: bool = False, as_absolute: bool = False) -> Union[float, str, None]:
    """
    Tries to interpret a word as an amount and returns a float if this succeeds
    Examples:
        >>> parse_amount('1')
        1.0
        >>> parse_amount('1.1')
        1.1
        >>> parse_amount('1. 11')
        1.11
        >>> parse_amount('Total:13,37')
        13.37
        >>> parse_amount(' 1.003,37')
        1003.37
        >>> parse_amount('13,3')
        13.3
        >>> parse_amount('31.12.99')
        None
        >>> parse_amount('10.000')
        10000.0
        >>> parse_amount('-13,37')
        -13.37
        >>> parse_amount('(1.003,37)')
        -1003.37
    """
    # remove leading and trailing spaces
    string = string.strip(" ")

    # detect parentheses-negative "(123)" and strip them
    if string.startswith("(") and string.endswith(")"):
        sign = -1  # negative number
        string = string[1:-1].strip(" ")
    else:
        sign = 1  # assume positive number

    # strip head and tail from everything except digits or '-'
    string = re_amount_non_digit.sub("", string)
    # remove spaces after decimal divider
    string = re_amount_trailing_space_after_comma.sub(r"\g<1>", string)  # keep the decimal separator
    # , -> .
    string = re_amount_comma_space.sub(".", string)
    # '.-' -> '.00' (handle this BEFORE checking for trailing minus)
    string = re_amount_dotdash.sub(".00", string)

    # detect leading or trailing minus and strip it
    if string.startswith("-"):
        sign = -1  # negative number
        string = string[1:].strip(" ")
    elif string.endswith("-"):
        sign = -1  # negative number
        string = string[:-1].strip(" ")

    # stop if we match no-go conditions
    if re_amount_invalid.match(string):
        return None
    # does format match monetary formats?
    if not re_amount_format.match(string):
        return None

    # grab the potential decimals
    if len(string) > 3 and string[-3] == ".":
        number, decimals = string[:-3], string[-3:]
    elif len(string) > 2 and string[-2] == ".":
        number, decimals = string[:-2], string[-2:]
    else:
        number = string
        decimals = ""

    # remove all separators
    number = number.replace(".", "")
    # cast to float and add the sign
    res_amount = float(number + decimals) * sign

    if as_absolute:
        res_amount = abs(res_amount)
    if as_string:
        return format_amount(res_amount)
    return res_amount


regex_strict_amount = regex.compile(
    r"""
    # Prefix
    ^(-?\p{Sc}?-?)
    # Separated digits
    (([1-9]\d{0,2}([ .,]\d{3})*|
    # Non-separated digits
    [1-9]\d*|
    # Decimal numbers starting with 0
    0)
    # Decimal digits
    [.,]\d{2})
    # Suffix
    (?:,-)?$
    """,
    flags=regex.VERBOSE,
)


def parse_strict_amount(string: str, as_string: bool = False, as_absolute: bool = False):
    """
    Tries to parse strict amount from the string and convert match to float.
    There's no upper limit.
    Valid cases examples:
    1.111.111,11
    111.111,11
    11.111,11
    1.111,11
    111,11
    11,11
    1,11
    0,11
    X,-
    €X,XX
    $X,XX
    Arguments:
        string {str} -- string from which the amounts should be parsed
    """
    amount = regex_strict_amount.match(string)

    if amount is None:
        return None

    sign = "-" if "-" in amount.group(1) else ""
    split_amount = amount.group(2).replace("-", "").replace(",", ".").replace(" ", ".").split(".")
    decimal_digits = split_amount[-1]
    digits = "".join(split_amount[:-1])
    result = "{}{}.{}".format(sign, digits, decimal_digits)

    res_amount = float(result)
    if as_absolute:
        res_amount = abs(res_amount)
    if as_string:
        return format_amount(res_amount)
    return res_amount
