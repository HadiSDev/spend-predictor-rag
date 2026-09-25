"""A total is not a line item."""
from __future__ import annotations

import json

import pytest

from ai_api.documents.images import DocumentImage
from ai_api.documents.vision import look_at


def _page() -> DocumentImage:
    return DocumentImage(media_type="image/png", content=b"page")


def _reply(lines: list[dict], **fields) -> str:
    body = {"line_items": lines}
    body.update(fields)
    return json.dumps(body)


def _read(lines: list[dict]):
    return look_at("", [_page()], complete=lambda m: _reply(lines))


def test_the_dsb_receipt_is_one_line_not_two():
    result = _read([
        {"description": "1 Voksen", "amount": "58,00 kr."},
        {"description": "Samlet pris", "amount": "58,00 kr."},
    ])

    assert [l.description for l in result.line_items] == ["1 Voksen"]
    assert sum(l.amount for l in result.line_items) == 58.0


def test_the_dsb_receipt_is_one_line_when_the_model_names_the_item():
    result = _read([
        {"item_name": "1 Voksen", "amount": "58,00 kr."},
        {"item_name": "Samlet pris", "amount": "58,00 kr."},
    ])

    assert [l.item_name for l in result.line_items] == ["1 Voksen"]
    assert sum(l.amount for l in result.line_items) == 58.0


@pytest.mark.parametrize(
    "label",
    ["Samlet pris", "I alt", "At betale", "Total", "Grand Total", "Subtotal"],
)
def test_a_named_summary_row_is_never_a_line_item(label):
    result = _read([
        {"item_name": "Widget", "amount": "10,00"},
        {"item_name": label, "amount": "10,00"},
    ])

    assert [l.item_name for l in result.line_items] == ["Widget"]


@pytest.mark.parametrize(
    "name",
    ["Total Station Kit", "Sumatra coffee", "Subtotal Analyser 3000"],
)
def test_a_named_product_containing_a_summary_word_is_kept(name):
    result = _read([{"item_name": name, "amount": "10,00"}])

    assert [l.item_name for l in result.line_items] == [name]


def test_a_lone_named_total_is_still_kept():
    result = _read([{"item_name": "Samlet pris", "amount": "58,00 kr."}])

    assert [l.item_name for l in result.line_items] == ["Samlet pris"]


@pytest.mark.parametrize(
    "label",
    [
        "Samlet pris", "Pris i alt", "I alt", "At betale", "Total DKK",
        "Total", "Subtotal", "Sub-total", "Grand Total", "Sum",
        "Amount due", "Balance due", "Order Total", "Total amount",
        "Gesamt", "Zwischensumme", "Gesamtbetrag",
        "TOTAL", "total:", "  Grand Total  ",
    ],
)
def test_a_summary_row_is_never_a_line_item(label):
    result = _read([
        {"description": "Widget", "amount": "10,00"},
        {"description": label, "amount": "10,00"},
    ])

    assert [l.description for l in result.line_items] == ["Widget"]


@pytest.mark.parametrize(
    "description",
    [
        "Total Station Kit",
        "Sumatra coffee beans 1kg",
        "Subtotal Analyser Pro",
        "Grand Piano Stand",
        "Summer tyres 205/55",
        "Totalizer valve",
    ],
)
def test_a_product_whose_name_contains_a_summary_word_is_kept(description):
    result = _read([{"description": description, "amount": "10,00"}])

    assert [l.description for l in result.line_items] == [description]


@pytest.mark.parametrize(
    "description",
    ["Shipping", "Shipping fee:", "Postage & Packing", "Handling fee", "Fragt"],
)
def test_a_charge_is_kept_because_it_is_in_the_total(description):
    result = _read([
        {"description": "Widget", "amount": "10,00"},
        {"description": description, "amount": "5,00"},
    ])

    assert len(result.line_items) == 2


def test_a_tax_row_is_not_a_line_item():
    result = _read([
        {"description": "Widget", "amount": "80,00"},
        {"description": "Moms 25%", "amount": "20,00"},
    ])

    assert [l.description for l in result.line_items] == ["Widget"]


def test_a_line_with_no_description_is_still_kept():
    result = _read([{"description": None, "amount": "58,00"}])

    assert len(result.line_items) == 1


def test_a_document_whose_only_row_is_a_total_keeps_it():
    result = _read([{"description": "Total", "amount": "58,00"}])

    assert [l.description for l in result.line_items] == ["Total"]
    assert result.line_items[0].amount == 58.0


def test_a_total_is_still_dropped_when_real_lines_stand_beside_it():
    result = _read([
        {"description": "Widget", "amount": "40,00"},
        {"description": "Gadget", "amount": "18,00"},
        {"description": "Total", "amount": "58,00"},
    ])

    assert [l.description for l in result.line_items] == ["Widget", "Gadget"]


def test_a_page_of_only_totals_beside_a_page_of_lines_still_drops_them():
    replies = [
        _reply([{"description": "Widget", "amount": "40,00"}]),
        _reply([{"description": "Total", "amount": "40,00"}]),
    ]
    pages = [_page(), _page()]
    result = look_at("", pages, complete=lambda m: replies.pop(0))

    assert [l.description for l in result.line_items] == ["Widget"]
