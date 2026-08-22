"""Rewrite European number formatting into an unambiguous form.

A Danish invoice writes 1919.20 as ``1 919,20`` — space for thousands, comma for
decimals. Printed beside a quantity column that reads

    Beskrivelse            Pris     Rabat  Antal   Grundlag   Moms
    DJI Osmo Nano 128GB    1 919,20  0,00      1   1 919,20   25,00%

a model has to guess whether ``1 919,20`` is one number or the quantity ``1``
followed by ``919,20``. On a real Elgiganten order confirmation it guessed the
latter, returned 919.2 for a 1919.20 line, and reconciliation rejected the whole
extraction — correctly, but the document was readable and we lost it.

Telling the model about Danish separators in the prompt is a hope. Removing the
ambiguity from the text is a fact, and a pure function can be tested where a
prompt cannot.

Two entry points, for the two paths:

* :func:`normalize_numbers` rewrites a **text layer** before the model reads it.
* :func:`parse_amount` reads back a **single amount as printed**, which is what
  the vision path uses: pixels cannot be rewritten, so the model transcribes the
  figure verbatim and the decision is made here instead of in a prompt.

Deliberately conservative. Every rewrite requires a **comma decimal** to be
present, because that is what marks the text as European in the first place:

* ``1 919,20`` / ``1 234 567,89`` — space (or non-breaking space) grouping.
* ``5.780,00`` / ``1.234.567,89`` — dot grouping. Unambiguous *only* because a
  comma decimal follows it; the dots cannot also be decimal points.
* ``919,20`` — a bare comma decimal.

A dot decimal (``1919.20``), US grouping (``1,919.20``), a date (``03.07.2026``)
and a long digit string are all left exactly as they are. Guessing at
``1.234`` — 1234 in Copenhagen, 1.234 in London — is the ambiguity this module
exists to remove, not one to resolve by coin flip.
"""
from __future__ import annotations

import re

#: The separators a PDF actually emits for grouping: a space or a non-breaking
#: space. A thin space shows up in some generators too.
_GROUP = "[ \u00a0\u2009\u202f]"

#: `1 919,20`, `1 234 567,89` — grouped digits with a comma decimal. The leading
#: group is 1-3 digits and every later group is exactly 3, so `1 1 919,20`
#: (quantity then amount) matches only the amount.
_GROUPED = re.compile(
    rf"(?<![\d,.])(\d{{1,3}}(?:{_GROUP}\d{{3}})+),(\d{{1,2}})(?![\d,.])"
)

#: `5.780,00`, `1.234.567,89` — dot grouping with a comma decimal. Safe to
#: rewrite precisely because the comma is present: a dot cannot be the decimal
#: separator when a comma already is. Without the comma this shape is `1.234`,
#: which stays untouched.
_DOT_GROUPED = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})+),(\d{1,2})(?![\d,.])")

#: `919,20` — a comma decimal with no grouping. Excludes a preceding digit,
#: comma or dot so it cannot bite into a US-grouped number like `1,919.20`.
_BARE = re.compile(r"(?<![\d,.])(\d+),(\d{1,2})(?![\d,.])")


def normalize_numbers(text: str) -> str:
    """Rewrite European amounts in ``text`` as plain ``1234.56`` figures."""
    text = _GROUPED.sub(
        lambda m: re.sub(_GROUP, "", m.group(1)) + "." + m.group(2), text
    )
    text = _DOT_GROUPED.sub(lambda m: m.group(1).replace(".", "") + "." + m.group(2), text)
    return _BARE.sub(lambda m: f"{m.group(1)}.{m.group(2)}", text)


#: What the whole cleaned figure must look like to be money: optional sign, then
#: digits, then at most one dot decimal. Anything else — a bare `1.234`, a
#: 13-digit barcode with no decimal, a date — is refused.
_MONEY = re.compile(r"^-?\d+(?:\.\d{1,2})?$")

#: A digit run this long with no decimal is an article number or a barcode, not
#: a price. The EKWB invoice returned `3831109813256` as a line total.
_MAX_PLAIN_DIGITS = 9

#: The figure inside a printed amount: a digit, then any run of digits and
#: separators, ending on a digit. Anchored on digits at both ends so a trailing
#: `kr.`'s dot or a leading symbol never joins the number.
_FIGURE = re.compile(rf"\d(?:[\d,.{_GROUP[1:-1]}]*\d)?")


def parse_amount(printed: object) -> float | None:
    """Read one amount exactly as printed, or refuse it.

    Returns ``None`` — never a guess — when the figure is ambiguous or is not a
    figure at all. A refused amount becomes a line with no amount, which
    reconciliation then reports as not adding up; a *guessed* one becomes a
    wrong number that reconciles by luck and is never questioned again.
    """
    if printed is None:
        return None
    if isinstance(printed, (int, float)) and not isinstance(printed, bool):
        return float(printed)

    text = str(printed).strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "-", "—", "–"}:
        return None

    text = text.replace("−", "-")  # U+2212 MINUS SIGN, which PDFs emit
    # Accounting parentheses and a leading minus both mean negative. Read before
    # the figure is isolated, since isolating it discards them.
    negative = (text.startswith("(") and text.endswith(")")) or text.lstrip(
        "€$£kr. "
    ).startswith("-")

    # The figure is *found*, not carved out by deleting everything around it:
    # `kr. 58,00` loses its letters but keeps the abbreviation's dot, and
    # `.58.00` is not a number. Currency symbols and codes ride along with the
    # amount on a real document — `DKK 5.780,00`, `€90.30`, `1 919,20 DKK`.
    found = _FIGURE.search(text)
    if not found:
        return None

    normalized = normalize_numbers(found.group(0))
    # A US-grouped figure is unambiguous once a dot decimal is present.
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d{1,2}", normalized):
        normalized = normalized.replace(",", "")
    normalized = re.sub(r"\s+", "", normalized)

    if not _MONEY.fullmatch(normalized):
        return None
    if "." not in normalized and len(normalized.lstrip("-")) > _MAX_PLAIN_DIGITS:
        return None

    value = float(normalized)
    return -value if negative and value > 0 else value
