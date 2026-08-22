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

Deliberately conservative. Only two shapes are rewritten, both of which require a
**comma decimal** to be present, because that is what marks the text as
European in the first place:

* ``1 919,20`` / ``1 234 567,89`` — space (or non-breaking space) grouping.
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
_GROUP = "[   ]"

#: `1 919,20`, `1 234 567,89` — grouped digits with a comma decimal. The leading
#: group is 1-3 digits and every later group is exactly 3, so `1 1 919,20`
#: (quantity then amount) matches only the amount.
_GROUPED = re.compile(
    rf"(?<![\d,.])(\d{{1,3}}(?:{_GROUP}\d{{3}})+),(\d{{1,2}})(?![\d,.])"
)

#: `919,20` — a comma decimal with no grouping. Excludes a preceding digit,
#: comma or dot so it cannot bite into a US-grouped number like `1,919.20`.
_BARE = re.compile(r"(?<![\d,.])(\d+),(\d{1,2})(?![\d,.])")


def normalize_numbers(text: str) -> str:
    """Rewrite European amounts in ``text`` as plain ``1234.56`` figures."""
    text = _GROUPED.sub(
        lambda m: re.sub(_GROUP, "", m.group(1)) + "." + m.group(2), text
    )
    return _BARE.sub(lambda m: f"{m.group(1)}.{m.group(2)}", text)
