"""A total is not a line item.

Two DSB receipts, identical in shape, one page each:

    Antal Produkt        Enhedspris      Sum
       1 Voksen           58,00 kr.
         Samlet pris      58,00 kr.     58,00 kr.
         Pris i alt                     58,00 kr.

One was read as a single 58,00 line and reconciled against its 58,00 posting.
The other returned `1 Voksen` **and** `Samlet pris` — 116,00 against the same
58,00 — and was rejected. The document is the same both times; only the model's
judgement about which rows are items differed.

That judgement should not be the model's to make twice. A row labelled with a
summary word is a summary in every invoice that has ever been written, so it is
dropped here, deterministically, where the rule can be tested — the same reason
`normalize_numbers` rewrites separators instead of asking the model nicely.

Two boundaries this must not cross, both pinned below:

* **Only whole labels.** "Total Station Kit" is a surveying instrument and
  "Sumatra coffee" is a coffee. Matching a summary word anywhere inside a
  description would silently delete real spend, which is far worse than the
  double-count it set out to fix.
* **A charge is not a summary.** Shipping, handling and fees are billed amounts
  that belong in the total, so they stay. Dropping them would make every invoice
  carrying postage fail to reconcile.
"""
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
    """The failure this exists for, in the shape it actually arrived in."""
    result = _read([
        {"description": "1 Voksen", "amount": "58,00 kr."},
        {"description": "Samlet pris", "amount": "58,00 kr."},
    ])

    assert [l.description for l in result.line_items] == ["1 Voksen"]
    assert sum(l.amount for l in result.line_items) == 58.0


def test_the_dsb_receipt_is_one_line_when_the_model_names_the_item():
    """The same receipt, in the shape the model returns *now*.

    A line's text moved from `description` to `item_name`, and this filter went
    on reading `description` — which is null on nearly every line the model
    produces. The filter silently stopped filtering: the DSB receipt counted
    `1 Voksen` **and** `Samlet pris`, summed to 116,00 against a 58,00 posting,
    and was rejected. Two more documents in the live corpus failed the same way,
    each at exactly twice its own total.

    Every case below duplicates the `description` tests deliberately. The old
    ones kept passing throughout, which is precisely why they caught nothing.
    """
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
    """Matched on the whole label, never as a substring — the rule the
    `description` tests pin, holding for the field that carries the text now."""
    result = _read([{"item_name": name, "amount": "10,00"}])

    assert [l.item_name for l in result.line_items] == [name]


def test_a_lone_named_total_is_still_kept():
    """The filter exists to stop double-counting; with nothing to double-count
    it has no work to do, and dropping the row throws the document away."""
    result = _read([{"item_name": "Samlet pris", "amount": "58,00 kr."}])

    assert [l.item_name for l in result.line_items] == ["Samlet pris"]


@pytest.mark.parametrize(
    "label",
    [
        # Danish, as printed on the receipts in this ledger.
        "Samlet pris", "Pris i alt", "I alt", "At betale", "Total DKK",
        # English.
        "Total", "Subtotal", "Sub-total", "Grand Total", "Sum",
        "Amount due", "Balance due", "Order Total", "Total amount",
        # German — Aquatuning and EK Waterblocks both invoice in it.
        "Gesamt", "Zwischensumme", "Gesamtbetrag",
        # Case and punctuation must not matter.
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
        # A summary word inside a real product name. Deleting these would be a
        # far worse bug than the double-count this rule fixes.
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
    """Postage is billed money. Dropping it fails every invoice that has any."""
    result = _read([
        {"description": "Widget", "amount": "10,00"},
        {"description": description, "amount": "5,00"},
    ])

    assert len(result.line_items) == 2


def test_a_tax_row_is_not_a_line_item():
    """VAT stated as its own row would break both gross and net reconciliation."""
    result = _read([
        {"description": "Widget", "amount": "80,00"},
        {"description": "Moms 25%", "amount": "20,00"},
    ])

    assert [l.description for l in result.line_items] == ["Widget"]


def test_a_line_with_no_description_is_still_kept():
    """Blank is not a summary word. A posting-derived line often has no text."""
    result = _read([{"description": None, "amount": "58,00"}])

    assert len(result.line_items) == 1


def test_a_document_whose_only_row_is_a_total_keeps_it():
    """The filter exists to stop double-counting. With one row there is nothing
    to double-count, and dropping it throws the document away.

    This reverses an earlier decision here, on evidence. Asked to read the DSB
    receipt, the model returned `1 Voksen` *and* `Samlet pris` on one run and
    only `Samlet pris` on the next. Discarding the second reading left the
    invoice on its ERP stand-in — strictly less than the document offered, since
    a lone total can only ever equal the document's own total and so cannot
    inflate anything.
    """
    result = _read([{"description": "Total", "amount": "58,00"}])

    assert [l.description for l in result.line_items] == ["Total"]
    assert result.line_items[0].amount == 58.0


def test_a_total_is_still_dropped_when_real_lines_stand_beside_it():
    """The rule only relaxes when relaxing costs nothing."""
    result = _read([
        {"description": "Widget", "amount": "40,00"},
        {"description": "Gadget", "amount": "18,00"},
        {"description": "Total", "amount": "58,00"},
    ])

    assert [l.description for l in result.line_items] == ["Widget", "Gadget"]


def test_a_page_of_only_totals_beside_a_page_of_lines_still_drops_them():
    """The judgement is made across the whole document, not page by page — a
    multi-page invoice prints its total on the last page and its items earlier."""
    replies = [
        _reply([{"description": "Widget", "amount": "40,00"}]),
        _reply([{"description": "Total", "amount": "40,00"}]),
    ]
    pages = [_page(), _page()]
    result = look_at("", pages, complete=lambda m: replies.pop(0))

    assert [l.description for l in result.line_items] == ["Widget"]
