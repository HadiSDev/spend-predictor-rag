"""What the vision path asks the model for, and what it decides itself."""
from __future__ import annotations

import json

from ai_api.documents.images import DocumentImage
from ai_api.documents.vision import VisionPage, look_at


def _page() -> DocumentImage:
    return DocumentImage(media_type="image/png", content=b"page")


def _reply(lines: list[dict], **fields) -> str:
    body = {"line_items": lines}
    body.update(fields)
    return json.dumps(body)


def test_the_model_is_asked_for_the_amount_as_printed():
    field = VisionPage.model_fields["line_items"]
    assert "as printed" in (field.description or "").lower()


def test_a_european_amount_transcribed_verbatim_is_read_correctly():
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
    reply = _reply([{"description": "EK-CryoFuel Clear", "amount": "3831109813256"}])

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.line_items[0].amount is None
    assert result.line_items[0].description == "EK-CryoFuel Clear"


def test_a_line_whose_amount_cannot_be_read_is_kept_without_one():
    reply = _reply([
        {"description": "Readable", "amount": "58,00"},
        {"description": "Unreadable", "amount": "3831109813256"},
    ])

    result = look_at("", [_page()], complete=lambda m: reply)

    assert [l.description for l in result.line_items] == ["Readable", "Unreadable"]
    assert [l.amount for l in result.line_items] == [58.0, None]


def test_a_line_with_no_text_is_still_a_line():
    reply = _reply([{"description": None, "amount": "58,00"}])

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.line_items[0].item_name is None
    assert result.line_items[0].description is None
    assert result.line_items[0].amount == 58.0


def test_a_plain_number_from_a_compliant_model_still_works():
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
    reply = _reply([], currency="null")

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.currency is None


def test_a_lowercase_currency_word_is_still_reported():
    reply = _reply([], currency="DKK")

    result = look_at("", [_page()], complete=lambda m: reply)

    assert result.currency == "DKK"
