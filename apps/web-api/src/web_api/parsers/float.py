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
from typing import Optional
from typing import Union

re_float_non_digit = re.compile(r"^[^\d\-(]+|[^\d\-)]+$")
re_float_trailing_or_leading_space_after_comma = re.compile(r"([,.])\s|\s([,.])")
re_float_dot_or_comma_dash = re.compile(r"[\.,]-")
re_float_invalid = re.compile(r"^0\d+|^[^\d]|[^\d]$")


def normalize_float(value: Union[str, float]):
    if isinstance(value, float):
        value = str(value)
        return value
    return value


def normalize_parse_float(value: Union[str, float], as_string: bool = False, as_absolute: bool = False):
    return parse_float(string=normalize_float(value), as_string=as_string, as_absolute=as_absolute)


def parse_float(string: str, as_string: bool = False, as_absolute: bool = False):
    """
    Tries to interpret a word as a float.
    Examples:
        >>> parse_float('1')
        1.0
        >>> parse_float('1.1')
        1.1
        >>> parse_float('1. 111')
        1.111
        >>> parse_float('Total:13,37')
        13.37
        >>> parse_float(' 1.003,1337')
        1003.1337
        >>> parse_float('13,3')
        13.3
        >>> parse_float('31.12.99')
        None
        >>> parse_float('10.000')
        10.0
    """
    # Remove leading and trailing spaces
    string = string.strip(" ")

    # Remove repeated spaces and non-space whitespace
    string = " ".join(string.split())

    # Remove spaces before or after decimal divider
    string = re_float_trailing_or_leading_space_after_comma.sub(r"\g<1>", string)

    # Strip head and tail from everything except digits or '-', ')', '('
    string = re_float_non_digit.sub("", string)

    # '.-' or ',-' -> '.00'.
    string = re_float_dot_or_comma_dash.sub(".00", string)

    # If '-' in head or tail or if amount is in parentheses the number is negative
    sign = 1.0
    if string.startswith("-") or string.endswith("-") or string.startswith("(") or string.endswith(")"):
        string = string.strip("-() ")
        sign = -1.0

    # Stop if we match no-go conditions.
    if string == "" or re_float_invalid.match(string):
        return None

    groups, separators = _analyse(string)

    if separators is None:
        # Found invalid character(s) during string analysis, so we stop.
        return None
    if len(separators) == 0:
        # It's an integer
        return _finalize(groups[0], None, sign, as_string, as_absolute)
    elif len(separators) == 1:
        # In case the last group has length 3 we can't know if we're looking at an integer or a float. We default to
        # float. For all other cases we must be looking at a float with the last group being the decimals. So either way
        # we interpret this case as a float.
        return _finalize(groups[0], groups[1], sign, as_string, as_absolute)
    else:
        if groups[0] == "0":
            # If the first group is 0 then more than a single separator makes the format invalid.
            return None

        if not all(len(g) == 3 for g in groups[1:-1]):
            # At least one inner group is not length 3, so the format is invalid.
            return None

        if len(groups[-1]) == 3:
            # With the final group at length 3 we can't immediately know if we're looking at an integer or a float. We
            # base our decision on the used separators.
            if separators[-1] in set("".join(separators[:-1])):
                # Must be a thousand separated integer.
                return _finalize("".join(groups), None, sign, as_string, as_absolute)
            else:
                # Last group must be decimals.
                return _finalize("".join(groups[:-1]), groups[-1], sign, as_string, as_absolute)
        else:
            # The last group must be decimals.
            return _finalize("".join(groups[:-1]), groups[-1], sign, as_string, as_absolute)


def _analyse(string: str):
    # Find groups and separators.
    groups = []
    separators = []
    current_group = ""
    current_separator = ""
    for c in string:
        if c in "0123456789":
            if len(current_separator) > 0:
                separators.append(current_separator)
                current_separator = ""
            current_group += c
        elif c in "., ":
            if len(current_group) > 0:
                groups.append(current_group)
                current_group = ""
            current_separator += c
        else:
            # Found invalid character, so we stop.
            return None, None

    if len(current_group) > 0:
        groups.append(current_group)
    if len(current_separator) > 0:
        separators.append(current_separator)

    return groups, separators


def _finalize(number: str, decimals: Optional[str], sign: float, as_string: bool, as_absolute: bool):
    if decimals is None:
        decimals = ""
    else:
        decimals = "." + decimals
    res_amount = float(number + decimals) * sign
    if as_absolute:
        res_amount = abs(res_amount)
    if as_string:
        return str(res_amount)
    return res_amount
