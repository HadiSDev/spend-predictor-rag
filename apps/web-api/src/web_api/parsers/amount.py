"""Amount parsing, vendored from `groundley-ai/packages/parsers`."""
import re
from typing import Union

import regex

re_amount_non_digit = re.compile(r"^[^\d-]+|[^\d-]+$")
re_amount_trailing_space_after_comma = re.compile(r"([,.])\s+")
re_amount_comma_space = re.compile(r",|\s")
re_amount_dotdash = re.compile(r"\.-")
re_amount_invalid = re.compile(r"^0\d+")
re_amount_strict = r"^\d{1,3}(\.\d{3})*(\.\d\d)?$"
re_amount_sloppy = r"^\d{1,7}(\.\d?\d)?$"
re_amount_format = re.compile("|".join([re_amount_strict, re_amount_sloppy]))


def format_amount(float_amount: float):
    if float_amount is not None:
        return f"{float_amount:.2f}"
    return None


def normalize_amount(value: Union[str, float]):
    if isinstance(value, float):
        value = format_amount(value)
        return value
    return value


def normalize_parse_amount(value: Union[str, float], as_string: bool = False, as_absolute: bool = False):
    return parse_amount(string=normalize_amount(value), as_string=as_string, as_absolute=as_absolute)


def parse_amount(string: str, as_string: bool = False, as_absolute: bool = False) -> Union[float, str, None]:
    """Interpret a word as an amount, returning a float on success."""
    string = string.strip(" ")

    if string.startswith("(") and string.endswith(")"):
        sign = -1
        string = string[1:-1].strip(" ")
    else:
        sign = 1

    string = re_amount_non_digit.sub("", string)
    string = re_amount_trailing_space_after_comma.sub(r"\g<1>", string)
    string = re_amount_comma_space.sub(".", string)
    string = re_amount_dotdash.sub(".00", string)

    if string.startswith("-"):
        sign = -1
        string = string[1:].strip(" ")
    elif string.endswith("-"):
        sign = -1
        string = string[:-1].strip(" ")

    if re_amount_invalid.match(string):
        return None
    if not re_amount_format.match(string):
        return None

    if len(string) > 3 and string[-3] == ".":
        number, decimals = string[:-3], string[-3:]
    elif len(string) > 2 and string[-2] == ".":
        number, decimals = string[:-2], string[-2:]
    else:
        number = string
        decimals = ""

    number = number.replace(".", "")
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
    """Tries to parse strict amount from the string and convert match to float."""
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
