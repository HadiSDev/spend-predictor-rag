"""What a document says about its own arithmetic."""
from __future__ import annotations

import io
import json

from reportlab.pdfgen import canvas

import ai_api.documents.extractor as extractor_mod
from ai_api.documents.extractor import extract_lines
from ai_api.documents.images import DocumentImage
from ai_api.documents.vision import build_messages, look_at
from ai_api.models import ExtractedInvoice, LineItem
from web_api.connectors.base import DocumentPayload


def test_a_line_printing_both_figures_records_both():
    line = LineItem(
        item_name="Aquacomputer Double Protect Ultra 5000ml",
        subtotal=29.31,
        vat_rate=25.0,
        tax_amount=7.33,
        amount=36.64,
    )

    assert line.subtotal == 29.31
    assert line.tax_amount == 7.33
    assert line.amount == 36.64
    assert line.vat_rate == 25.0


def test_a_line_printing_one_figure_leaves_the_tax_fields_null():
    line = LineItem(item_name="1 Voksen", amount=58.0)

    assert line.amount == 58.0
    assert line.subtotal is None
    assert line.tax_amount is None
    assert line.discount is None


def test_a_stated_discount_is_recorded_rather_than_netted_away():
    line = LineItem(item_name="Apple adapter 96W", amount=484.0, discount=15.0)

    assert line.discount == 15.0
    assert line.amount == 484.0, "the printed total is not rewritten"


def _payload(text: str):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 750
    for line in text.splitlines():
        c.drawString(60, y, line)
        y -= 16
    c.save()
    return DocumentPayload(
        content=buf.getvalue(), media_type="application/pdf", filename="inv.pdf"
    )


def test_the_documents_own_totals_are_carried():
    def _kickoff(prompt: str) -> ExtractedInvoice:
        return ExtractedInvoice(
            vendor_name="Aquatuning GmbH",
            currency="EUR",
            subtotal=83.88,
            tax=20.97,
            total=104.85,
            line_items=[LineItem(item_name="Loop Cleaner", amount=31.41)],
        )

    result = extract_lines(_payload("Total amount EUR 104.85"), kickoff=_kickoff)

    assert result.total == 104.85
    assert result.tax == 20.97
    assert result.subtotal == 83.88


def test_a_document_with_no_totals_block_records_null_not_zero():
    def _kickoff(prompt: str) -> ExtractedInvoice:
        return ExtractedInvoice(
            vendor_name="DSB",
            currency="DKK",
            line_items=[LineItem(item_name="1 Voksen", amount=58.0)],
        )

    result = extract_lines(_payload("1 Voksen  58,00"), kickoff=_kickoff)

    assert result.total is None
    assert result.tax is None
    assert result.subtotal is None


def test_a_stated_zero_is_kept_as_a_zero():
    def _kickoff(prompt: str) -> ExtractedInvoice:
        return ExtractedInvoice(
            vendor_name="Acme", total=100.0, tax=0.0,
            line_items=[LineItem(item_name="Thing", amount=100.0)],
        )

    result = extract_lines(_payload("Total 100.00  VAT 0.00"), kickoff=_kickoff)

    assert result.tax == 0.0, "a document stating no VAT said something"


def _image(n: int):
    return DocumentImage(media_type="image/png", content=f"page-{n}".encode())


def _replies(*bodies):
    """A `complete` seam handing back one canned reply per page, in order."""
    queue = [json.dumps(b) for b in bodies]

    def _complete(messages):
        return queue.pop(0)

    return _complete


def test_a_line_read_off_a_page_carries_its_tax_figures():
    merged = look_at(
        "",
        [_image(1)],
        complete=_replies(
            {
                "vendor_name": "Aquatuning GmbH",
                "currency": "EUR",
                "line_items": [
                    {
                        "item_name": "Loop Cleaner",
                        "subtotal": "25,13",
                        "tax_amount": "6,28",
                        "amount": "31,41",
                        "discount": "1,50",
                    }
                ],
            }
        ),
    )

    line = merged.line_items[0]
    assert line.subtotal == 25.13
    assert line.tax_amount == 6.28
    assert line.discount == 1.50
    assert line.amount == 31.41


def test_a_totals_block_on_the_last_page_is_the_documents_answer():
    merged = look_at(
        "",
        [_image(1), _image(2)],
        complete=_replies(
            {
                "vendor_name": "Aquatuning GmbH",
                "currency": "EUR",
                "line_items": [{"item_name": "Loop Cleaner", "amount": "31,41"}],
            },
            {
                "line_items": [{"item_name": "Wärmeleitpaste", "amount": "20,90"}],
                "subtotal": "83,88",
                "tax": "20,97",
                "total": "104,85",
            },
        ),
    )

    assert merged.total == 104.85
    assert merged.tax == 20.97
    assert merged.subtotal == 83.88
    assert [l.item_name for l in merged.line_items] == ["Loop Cleaner", "Wärmeleitpaste"]


def test_no_page_stating_a_total_yields_no_total():
    merged = look_at(
        "",
        [_image(1)],
        complete=_replies(
            {"vendor_name": "DSB", "line_items": [{"item_name": "1 Voksen", "amount": "58,00"}]}
        ),
    )

    assert merged.total is None


def test_both_paths_read_the_same_document_to_the_same_answer():
    figures = dict(
        vendor_name="Aquatuning GmbH", currency="EUR",
        subtotal=83.88, tax=20.97, total=104.85,
    )

    def _kickoff(prompt: str) -> ExtractedInvoice:
        return ExtractedInvoice(
            line_items=[LineItem(item_name="Loop Cleaner", subtotal=25.13,
                                 tax_amount=6.28, amount=31.41)],
            **figures,
        )

    from_text = extract_lines(_payload("Total amount EUR 104.85"), kickoff=_kickoff)

    def _look(prompt, images):
        return look_at(prompt, images, complete=_replies({
            **figures,
            "line_items": [{"item_name": "Loop Cleaner", "subtotal": "25,13",
                            "tax_amount": "6,28", "amount": "31,41"}],
        }))

    scan = DocumentPayload(content=b"\x89PNG fake", media_type="image/png", filename="scan.png")

    def _content(payload):
        return extractor_mod.DocumentContent(
            images=(DocumentImage(media_type="image/png", content=b"x"),)
        )

    original = extractor_mod.document_content
    extractor_mod.document_content = _content
    try:
        from_vision = extract_lines(scan, look=_look)
    finally:
        extractor_mod.document_content = original

    assert from_text.model_dump() == from_vision.model_dump()


def test_the_text_path_asks_for_totals_block_charges():
    seen: list[str] = []

    def _kickoff(prompt: str) -> ExtractedInvoice:
        seen.append(prompt)
        return ExtractedInvoice(vendor_name="X", total=1.0,
                                line_items=[LineItem(item_name="Y", amount=1.0)])

    extract_lines(_payload("shipping cost incl. VAT EUR 15.90"), kickoff=_kickoff)

    prompt = seen[0].lower()
    assert "shipping" in prompt
    assert "discount" in prompt, "the exclusion has to travel with the rule"


def test_the_vision_path_asks_for_the_same_thing():
    messages = build_messages(DocumentImage(media_type="image/png", content=b"x"))
    text = messages[0]["content"][0]["text"].lower()

    assert "shipping" in text
    assert "discount" in text


def test_a_charge_line_is_an_ordinary_line():
    def _kickoff(prompt: str) -> ExtractedInvoice:
        return ExtractedInvoice(
            vendor_name="Aquatuning GmbH", currency="EUR", total=104.85,
            line_items=[
                LineItem(item_name="Loop Cleaner", amount=31.41),
                LineItem(item_name="Wärmeleitpaste", amount=20.90),
                LineItem(item_name="Double Protect Ultra", amount=36.64),
                LineItem(item_name="Shipping", amount=15.90),
            ],
        )

    result = extract_lines(_payload("x"), kickoff=_kickoff)

    assert len(result.lines) == 4
    assert sum(l.amount for l in result.lines) == 104.85
    assert set(result.lines[3].model_dump()) == set(result.lines[0].model_dump())
