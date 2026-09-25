"""Rewrite European number formatting into an unambiguous form."""
from __future__ import annotations

import re

from web_api.parsers.amount import normalize_parse_amount

_GROUP = "[ \u00a0\u2009\u202f]"

_GROUPED = re.compile(
    rf"(?<![\d,.])(\d{{1,3}}(?:{_GROUP}\d{{3}})+),(\d{{1,2}})(?![\d,.])"
)

_DOT_GROUPED = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})+),(\d{1,2})(?![\d,.])")

_BARE = re.compile(r"(?<![\d,.])(\d+),(\d{1,2})(?![\d,.])")


def normalize_numbers(text: str) -> str:
    """Rewrite European amounts in ``text`` as plain ``1234.56`` figures."""
    text = _GROUPED.sub(
        lambda m: re.sub(_GROUP, "", m.group(1)) + "." + m.group(2), text
    )
    text = _DOT_GROUPED.sub(lambda m: m.group(1).replace(".", "") + "." + m.group(2), text)
    return _BARE.sub(lambda m: f"{m.group(1)}.{m.group(2)}", text)


_UNICODE_MINUS = "\u2212"


def parse_amount(printed: object) -> float | None:
    """Read one printed amount as money, or refuse it."""
    if printed is None:
        return None
    if isinstance(printed, bool):
        return None
    if isinstance(printed, (int, float)):
        return float(printed)

    text = str(printed).strip().replace(_UNICODE_MINUS, "-")
    if not text:
        return None
    try:
        return normalize_parse_amount(text)
    except Exception:  # noqa: BLE001
        return None
