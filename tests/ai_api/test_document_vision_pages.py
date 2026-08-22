"""Reading a multi-page document: one page per request, then merged.

A model handed eight images in one message attends to none of them properly —
the detail that matters on an invoice (a line's amount, in a column, in small
type) is exactly what degrades first. So each page is its own request, with its
own full attention, and the pages are merged here rather than by the model.

Merging is where the judgement lives, and these tests pin it:

* **Lines concatenate in page order.** A two-page invoice's lines are the first
  page's followed by the second's, and nothing deduplicates them — a supplier
  who bills the same item twice has billed it twice, and a repeated line is not
  ours to decide is a mistake.
* **A header field is taken from the first page that states it.** The supplier,
  the invoice number and the currency are printed on page one; a later page
  restating them adds nothing, and a later page *omitting* them must not erase
  what page one said.
* **A total is taken from the last page that states it.** That is where a total
  is printed, and an earlier page's figure is a running subtotal.
* **One unreadable page does not lose the rest.** A terms-and-conditions page
  that returns junk must not discard a good first page; reconciliation is the
  guard that catches an incomplete read, and it can only do that if the read
  survives to be checked. Every dropped page is logged, and a document whose
  pages *all* fail is a failure.
"""
from __future__ import annotations

import json

import pytest

from ai_api.documents.images import DocumentImage
from ai_api.documents.vision import VisionPage, VisionUnreadableError, look_at


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
    """A fragment read as a whole invoice invents the totals it cannot see."""
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
    """Billing the same item twice is the supplier's statement, not our error."""
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
    """A total is printed at the end; an earlier figure is a running subtotal."""
    replies = [_reply(total=100.0), _reply(total=2399.0)]

    result = look_at("", [_page(1), _page(2)], complete=lambda m: replies.pop(0))

    assert result.total == 2399.0


def test_a_page_that_states_no_lines_contributes_none_and_breaks_nothing():
    replies = [
        _reply(line_items=[_line("Monitor", 3200.0)]),
        _reply(line_items=[]),  # a terms-and-conditions page
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
    """One page is the whole document, and saying otherwise invites hedging."""
    prompts: list[str] = []

    def _complete(messages):
        prompts.append(
            next(p["text"] for p in messages[0]["content"] if p["type"] == "text")
        )
        return _reply()

    look_at("", [_page(1)], complete=_complete)

    assert "page 1 of 1" not in prompts[0]


# -- A page is a fragment, and a fragment has no required fields -------------


def test_a_page_that_names_no_supplier_is_still_read():
    """The prompt says "leave what this page does not state as null" — so a
    schema that requires the supplier rejects the model's honest answer.

    This is the bug that made every real screenshot fail: the model read the
    document correctly, returned well-formed JSON with a null `vendor_name`,
    and our own required-field validation threw the whole page away.
    """
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
    """Page 1 of 5 shows no total. That is not a failed reading."""
    reply = json.dumps({"line_items": [_line("Cable", 99.0)], "total": None})

    result = look_at("", [_page(1)], complete=lambda m: reply)

    assert [l.description for l in result.line_items] == ["Cable"]


def test_a_page_with_no_fields_at_all_is_still_a_reading():
    """An empty page reads as empty, not as an outage."""
    result = look_at("", [_page(1)], complete=lambda m: "{}")

    assert result.line_items == []


def test_the_page_schema_asks_for_nothing_mandatory():
    """The hint the model is shown must match what we will accept from it."""
    for name, field in VisionPage.model_fields.items():
        assert not field.is_required(), f"{name} is required of a single page"
