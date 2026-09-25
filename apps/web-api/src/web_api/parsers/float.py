"""Float parsing, vendored from `groundley-ai/packages/parsers`."""
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
    """Tries to interpret a word as a float."""
    string = string.strip(" ")

    string = " ".join(string.split())

    string = re_float_trailing_or_leading_space_after_comma.sub(r"\g<1>", string)

    string = re_float_non_digit.sub("", string)

    string = re_float_dot_or_comma_dash.sub(".00", string)

    sign = 1.0
    if string.startswith("-") or string.endswith("-") or string.startswith("(") or string.endswith(")"):
        string = string.strip("-() ")
        sign = -1.0

    if string == "" or re_float_invalid.match(string):
        return None

    groups, separators = _analyse(string)

    if separators is None:
        return None
    if len(separators) == 0:
        return _finalize(groups[0], None, sign, as_string, as_absolute)
    elif len(separators) == 1:
        return _finalize(groups[0], groups[1], sign, as_string, as_absolute)
    else:
        if groups[0] == "0":
            return None

        if not all(len(g) == 3 for g in groups[1:-1]):
            return None

        if len(groups[-1]) == 3:
            if separators[-1] in set("".join(separators[:-1])):
                return _finalize("".join(groups), None, sign, as_string, as_absolute)
            else:
                return _finalize("".join(groups[:-1]), groups[-1], sign, as_string, as_absolute)
        else:
            return _finalize("".join(groups[:-1]), groups[-1], sign, as_string, as_absolute)


def _analyse(string: str):
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
