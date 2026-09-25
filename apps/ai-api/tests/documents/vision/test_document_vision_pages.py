"""Reading a multi-page document: one page per request, then merged."""
from __future__ import annotations

import json

import pytest

from ai_api.documents.errors import VisionUnreadableError
from ai_api.documents.images import DocumentImage
from ai_api.documents.vision import VisionPage, look_at


def _page(n: int) -> DocumentImage:
    return DocumentImage(media_type="image/png", content=f"page-{n}".encode())


def _reply(**fields) -> str:
    body = {"vendor_name": "Acme", "total": 0.0, "line_items": []}
    body.update(fields)
    return json.dumps(body)


def _line(description: str, amount: float) -> dict:
    return {"description": description, "amount": amount}


def test_each_page_is_its_own_request():
    pages = [_page(1), _page(2), _page(3)]
    calls: list[list[dict]] = []

    def _complete(messages):
        calls.append(messages)
        return _reply()

    look_at("", pages, complete=_complete)

    assert len(calls) == 3, "eight images in one message is what this avoids"


def test_each_request_carries_exactly_one_page():
    calls: list[list[dict]] = []

    def _complete(messages):
        calls.append(messages)
        return _reply()

    look_at("", [_page(1), _page(2)], complete=_complete)

    for messages in calls:
        images = [
            part for part in messages[0]["content"] if part["type"] == "image_url"
        ]
        assert len(images) == 1


def test_a_page_is_told_which_page_it_is():
    prompts: list[str] = []

    def _complete(messages):
        prompts.append(
            next(p["text"] for p in messages[0]["content"] if p["type"] == "text")
        )
        return _reply()

    look_at("", [_page(1), _page(2), _page(3)], complete=_complete)

    assert "page 2 of 3" in prompts[1]


def test_lines_from_every_page_are_kept_in_page_order():
    replies = [
        _reply(line_items=[_line("Monitor", 3200.0)]),
        _reply(line_items=[_line("Cable", 99.0), _line("Stand", 450.0)]),
    ]

    result = look_at("", [_page(1), _page(2)], complete=lambda m: replies.pop(0))

    assert [l.description for l in result.line_items] == ["Monitor", "Cable", "Stand"]


def test_a_repeated_line_is_not_deduplicated():
    replies = [
        _reply(line_items=[_line("Support hour", 750.0)]),
        _reply(line_items=[_line("Support hour", 750.0)]),
    ]

    result = look_at("", [_page(1), _page(2)], complete=lambda m: replies.pop(0))

    assert len(result.line_items) == 2


def test_a_header_field_comes_from_the_first_page_that_states_it():
    replies = [
        _reply(vendor_name="Elgiganten", currency="DKK", invoice_number="2125165980"),
        _reply(vendor_name="Acme", currency="EUR", invoice_number="OTHER"),
    ]

    result = look_at("", [_page(1), _page(2)], complete=lambda m: replies.pop(0))

    assert result.currency == "DKK"
    assert result.invoice_number == "2125165980"
    assert result.vendor_name == "Elgiganten"


def test_a_later_page_omitting_a_header_field_does_not_erase_it():
    replies = [
        _reply(currency="DKK", invoice_number="IN-1"),
        _reply(currency=None, invoice_number=None),
    ]

    result = look_at("", [_page(1), _page(2)], complete=lambda m: replies.pop(0))

    assert result.currency == "DKK"
    assert result.invoice_number == "IN-1"


def test_the_total_comes_from_the_last_page_that_states_one():
    replies = [_reply(total=100.0), _reply(total=2399.0)]

    result = look_at("", [_page(1), _page(2)], complete=lambda m: replies.pop(0))

    assert result.total == 2399.0


def test_a_page_that_states_no_lines_contributes_none_and_breaks_nothing():
    replies = [
        _reply(line_items=[_line("Monitor", 3200.0)]),
        _reply(line_items=[]),
    ]

    result = look_at("", [_page(1), _page(2)], complete=lambda m: replies.pop(0))

    assert [l.description for l in result.line_items] == ["Monitor"]


def test_one_unreadable_page_does_not_discard_the_others(caplog):
    replies = ["not json at all", _reply(line_items=[_line("Monitor", 3200.0)])]

    with caplog.at_level("WARNING"):
        result = look_at("", [_page(1), _page(2)], complete=lambda m: replies.pop(0))

    assert [l.description for l in result.line_items] == ["Monitor"]
    assert "page 1" in caplog.text, "a dropped page is never dropped silently"


def test_a_document_whose_pages_all_fail_is_a_failure():
    with pytest.raises(VisionUnreadableError):
        look_at("", [_page(1), _page(2)], complete=lambda m: "not json at all")


def test_a_single_page_document_is_not_told_it_is_page_one_of_one():
    prompts: list[str] = []

    def _complete(messages):
        prompts.append(
            next(p["text"] for p in messages[0]["content"] if p["type"] == "text")
        )
        return _reply()

    look_at("", [_page(1)], complete=_complete)

    assert "page 1 of 1" not in prompts[0]


def test_a_page_that_names_no_supplier_is_still_read():
    reply = json.dumps({
        "vendor_name": None,
        "invoice_date": "22. maj 2026",
        "currency": "DKK",
        "line_items": [_line("Roskilde St.", 58.0)],
        "total": None,
    })

    result = look_at("", [_page(1)], complete=lambda m: reply)

    assert [l.description for l in result.line_items] == ["Roskilde St."]
    assert result.currency == "DKK"


def test_a_page_stating_no_total_is_still_read():
    reply = json.dumps({"line_items": [_line("Cable", 99.0)], "total": None})

    result = look_at("", [_page(1)], complete=lambda m: reply)

    assert [l.description for l in result.line_items] == ["Cable"]


def test_a_page_with_no_fields_at_all_is_still_a_reading():
    result = look_at("", [_page(1)], complete=lambda m: "{}")

    assert result.line_items == []


def test_the_page_schema_asks_for_nothing_mandatory():
    for name, field in VisionPage.model_fields.items():
        assert not field.is_required(), f"{name} is required of a single page"
