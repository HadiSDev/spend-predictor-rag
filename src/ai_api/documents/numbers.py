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

from web_api.parsers.amount import normalize_parse_amount

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


#: U+2212 MINUS SIGN, which PDFs emit where a keyboard would type a hyphen. The
#: vendored parser reads a hyphen and strips anything else as decoration, so a
#: minus written this way would silently lose its sign — a credit note becoming
#: a charge. Normalized here rather than in the parser, which is kept verbatim.
_UNICODE_MINUS = "\u2212"


def parse_amount(printed: object) -> float | None:
    """Read one printed amount as money, or refuse it.

    A thin wrapper over :func:`web_api.parsers.amount.normalize_parse_amount`,
    vendored from the `groundley-ai` parsers package. That parser analyses the
    figure's groups and separators rather than pattern-matching a handful of
    shapes, which is why it gets the cases this module previously could not:

    * ``5.780 kr.`` is 5780, not 5.78 — a dot group of three is thousands, since
      no ordinary currency carries three decimal places. A real DSB receipt was
      refused on the old hand-rolled rule and cost us the document.
    * ``31.12.99`` is a date and yields nothing, where a looser reading would
      have produced 31.12 and quietly wrong spend.
    * ``1.003,37``, ``1 919,20``, ``1,919.20``, ``(1.003,37)`` and ``13,37`` all
      resolve, in whichever convention the supplier printed.
    * A 13-digit barcode is not money, so an EKWB article number stays refused.

    Returns ``None`` rather than a guess, and ``None`` becomes a line with no
    amount — which reconciliation reports as not adding up. A *guessed* amount
    would reconcile by luck and never be questioned again.
    """
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
    except Exception:  # noqa: BLE001 - a malformed figure is not a crash
        return None
