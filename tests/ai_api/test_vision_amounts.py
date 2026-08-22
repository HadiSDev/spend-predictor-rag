"""What the vision path asks the model for, and what it decides itself.

The text path removes European number ambiguity *before* the model reads it, by
rewriting the text layer. Pixels cannot be rewritten, so the vision path does the
same job on the way back: the model transcribes each amount **exactly as
printed**, as a string, and :func:`ai_api.documents.numbers.parse_amount` turns
it into a figure. The decision moves out of a prompt, which can only be hoped at,
and into a pure function that is tested.

Both failures behind this are real, from the dev org's own ledger:

* A DSB receipt printing `5.780,00` came back as `5.78`. The model had been
  handed the whole judgement and made the wrong call on a separator.
* An EKWB invoice came back with `3831109813256` — the product's barcode — as a
  line total, and the schema's `float` accepted it without a murmur.

So a line whose amount cannot be read is kept **with no amount** rather than
dropped or guessed at. Dropping it hides money; guessing invents it. Keeping it
amount-less leaves the invoice visibly short, which is exactly what
reconciliation exists to catch.
"""
from __future__ import annotations

import json

from ai_api.documents.vision import VisionPage, look_at
from ai_api.documents.images import DocumentImage


def _page() -> DocumentImage:
    return DocumentImage(media_type="image/png", content=b"page")


def _reply(lines: list[dict], **fields) -> str:
    body = {"line_items": lines}
    body.update(fields)
    return json.dumps(body)


def test_the_model_is_asked_for_the_amount_as_printed():
    """A string field is what makes `5.780,00` survive the trip back to us."""
    field = VisionPage.model_fields["line_items"]
    assert "as printed" in (field.description or "").lower()


def test_a_european_amount_transcribed_verbatim_is_read_correctly():
    """The DSB failure: `5.780,00` must not become 5.78."""
    reply = _reply([{"description": "DSB Commute", "amount": "5.780,00"}])

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.line_items[0].amount == 5780.0


def test_a_space_grouped_amount_is_read_correctly():
    reply = _reply([{"description": "DJI Osmo Nano", "amount": "1 919,20"}])

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.line_items[0].amount == 1919.20


def test_a_currency_symbol_travels_with_the_figure():
    reply = _reply([{"description": "Sub", "amount": "kr. 58,00"}])

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.line_items[0].amount == 58.0


def test_a_barcode_is_not_accepted_as_an_amount():
    """The EKWB failure: a 13-digit article number is not a price."""
    reply = _reply([{"description": "EK-CryoFuel Clear", "amount": "3831109813256"}])

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.line_items[0].amount is None
    assert result.line_items[0].description == "EK-CryoFuel Clear"


def test_a_line_whose_amount_cannot_be_read_is_kept_without_one():
    """Dropped hides money; guessed invents it; kept-and-short reconciles false."""
    reply = _reply([
        {"description": "Readable", "amount": "58,00"},
        {"description": "Unreadable", "amount": "1.234"},
    ])

    result = look_at("", [_page()], complete=lambda m: reply)

    assert [l.description for l in result.line_items] == ["Readable", "Unreadable"]
    assert [l.amount for l in result.line_items] == [58.0, None]


def test_a_line_with_no_description_is_still_a_line():
    reply = _reply([{"description": None, "amount": "58,00"}])

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.line_items[0].description == ""
    assert result.line_items[0].amount == 58.0


def test_a_plain_number_from_a_compliant_model_still_works():
    """Some replies obey the float schema anyway. That must not regress."""
    reply = _reply([{"description": "Sub", "amount": 90.3}])

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.line_items[0].amount == 90.3


def test_the_documents_own_totals_are_read_the_same_way():
    reply = _reply([], total="5.780,00", tax="1.156,00", subtotal="4.624,00")

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.total == 5780.0
    assert result.tax == 1156.0
    assert result.subtotal == 4624.0


def test_a_literal_null_string_is_not_a_currency():
    """A real reply contained `"currency": "null"`. That is not a currency."""
    reply = _reply([], currency="null")

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.currency is None


def test_a_lowercase_currency_word_is_still_reported():
    """`kr` is what a Danish receipt prints; correcting it is not our job here."""
    reply = _reply([], currency="DKK")

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.currency == "DKK"
