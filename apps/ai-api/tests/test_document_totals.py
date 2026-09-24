"""What a document says about its own arithmetic.

The rule this file exists for: **gross-versus-net is read, never inferred.**

An Aquatuning invoice prints its line prices VAT-inclusive (88,95), states a
shipping charge only in its totals block (15,90) and a total of 104,85, and its
Danish posting carries the net 83,88 with `tax = 0.00`. Every figure is correct
and the document is internally exact — `(88,95 + 15,90) / 1,25 = 83,88` — yet a
rule comparing the document's lines against the ERP's total rejected the whole
extraction and reported it as a reading failure.

Reading more of the document is the fix. A document that prints both a net and a
gross figure has both taken, so nothing downstream has to decide which
convention a column follows.
"""
from __future__ import annotations

from ai_api.models import LineItem


def test_a_line_printing_both_figures_records_both():
    """Neither figure is derived from the other — both are transcribed."""
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
    """A receipt prints one number per line. Absent is not zero."""
    line = LineItem(item_name="1 Voksen", amount=58.0)

    assert line.amount == 58.0
    assert line.subtotal is None
    assert line.tax_amount is None
    assert line.discount is None


def test_a_stated_discount_is_recorded_rather_than_netted_away():
    """The line's total stays the figure the document printed.

    Netting the discount into the amount would destroy the evidence and make
    the line disagree with the page it was read from.
    """
    line = LineItem(item_name="Apple adapter 96W", amount=484.0, discount=15.0)

    assert line.discount == 15.0
    assert line.amount == 484.0, "the printed total is not rewritten"


# -- The document's own totals block -----------------------------------------
#
# Read past and discarded until now, which is why the only figure available to
# reconcile against belonged to a different system.


def _payload(text: str):
    import io

    from reportlab.pdfgen import canvas

    from web_api.connectors.base import DocumentPayload

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
    """Aquatuning's block, verbatim: the figures that explain the invoice."""
    from ai_api.documents.extractor import extract_lines
    from ai_api.models import ExtractedInvoice

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
    """"Nothing to compare" and "compared and agreed" must stay distinguishable.

    A stated zero is a claim; an absent figure is not. Folding the second into
    the first makes a document nobody could read look like one that balances.
    """
    from ai_api.documents.extractor import extract_lines
    from ai_api.models import ExtractedInvoice

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
    from ai_api.documents.extractor import extract_lines
    from ai_api.models import ExtractedInvoice

    def _kickoff(prompt: str) -> ExtractedInvoice:
        return ExtractedInvoice(
            vendor_name="Acme", total=100.0, tax=0.0,
            line_items=[LineItem(item_name="Thing", amount=100.0)],
        )

    result = extract_lines(_payload("Total 100.00  VAT 0.00"), kickoff=_kickoff)

    assert result.tax == 0.0, "a document stating no VAT said something"


# -- The vision path must carry the same fields, or silently lose them --------
#
# The easiest thing in this change to forget and the hardest to notice
# afterwards: a text-path document would carry the totals block and a scanned
# one would not, and the only symptom would be scanned invoices reconciling
# worse than text ones. Nothing in the product would say why.


def _image(n: int):
    from ai_api.documents.images import DocumentImage

    return DocumentImage(media_type="image/png", content=f"page-{n}".encode())


def _replies(*bodies):
    """A `complete` seam handing back one canned reply per page, in order."""
    import json

    queue = [json.dumps(b) for b in bodies]

    def _complete(messages):
        return queue.pop(0)

    return _complete


def test_a_line_read_off_a_page_carries_its_tax_figures():
    """Transcribed as printed, then read by `parse_amount` — never by the model.

    `5.780,00` came back from a model asked to normalize separators as `5.78`.
    The new fields are money like every other, so they take the same route.
    """
    from ai_api.documents.vision import look_at

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
    """An earlier page's total is a running subtotal; the last one stated wins."""
    from ai_api.documents.vision import look_at

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
    """Not zero. A scan of a receipt that prints no total states no total.

    The merge invented `0.0` here because the whole-invoice schema demanded a
    figure, which made "the document printed nothing" arrive downstream as "the
    document printed zero" — and the reconciliation rule now turns on exactly
    that difference.
    """
    from ai_api.documents.vision import look_at

    merged = look_at(
        "",
        [_image(1)],
        complete=_replies(
            {"vendor_name": "DSB", "line_items": [{"item_name": "1 Voksen", "amount": "58,00"}]}
        ),
    )

    assert merged.total is None


def test_both_paths_read_the_same_document_to_the_same_answer():
    """The merge asymmetry, pinned.

    Nothing downstream of `extract_lines` may be able to tell how a document was
    read. If the two paths ever disagree about which fields survive, this is the
    test that says so — the alternative is finding out from a month of scanned
    invoices reconciling worse than text ones.
    """
    from ai_api.documents.extractor import extract_lines
    from ai_api.models import ExtractedInvoice

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
        from ai_api.documents.vision import look_at

        return look_at(prompt, images, complete=_replies({
            **figures,
            "line_items": [{"item_name": "Loop Cleaner", "subtotal": "25,13",
                            "tax_amount": "6,28", "amount": "31,41"}],
        }))

    from ai_api.documents.images import DocumentImage
    from web_api.connectors.base import DocumentPayload

    import ai_api.documents.extractor as extractor_mod

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


# -- A charge stated in the totals block is spend -----------------------------
#
# €15,90 of freight left the company. Dropping it on the floor is spend no
# report can see, and it is also why a correctly-read invoice could not
# reconcile: a charge that exists only in the totals block cannot be summed from
# any set of line items.
#
# The instruction is pinned through the caller, not read off a constant. A
# prompt input nobody exercises is a prompt input that quietly stops being sent
# — which is exactly how the categorizer came to read a supplier and an amount
# and nothing else.


def test_the_text_path_asks_for_totals_block_charges():
    from ai_api.documents.extractor import extract_lines
    from ai_api.models import ExtractedInvoice

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
    """Or a scanned invoice loses freight that a text one keeps."""
    from ai_api.documents.images import DocumentImage
    from ai_api.documents.vision import build_messages

    messages = build_messages(DocumentImage(media_type="image/png", content=b"x"))
    text = messages[0]["content"][0]["text"].lower()

    assert "shipping" in text
    assert "discount" in text


def test_a_charge_line_is_an_ordinary_line():
    """Nothing marks it. Whether money went on a product or on delivering the
    product is a categorization question, not a reason for two kinds of line."""
    from ai_api.documents.extractor import extract_lines
    from ai_api.models import ExtractedInvoice

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
    # No flag, no separate collection, no marker of any kind.
    assert set(result.lines[3].model_dump()) == set(result.lines[0].model_dump())
