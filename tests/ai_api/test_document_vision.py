"""Reading a document the text layer cannot reach: photos, screenshots, scans.

Half of the dev org's unread invoices are not broken documents. They are a PNG
screenshot of a subscription receipt, a JPEG photo of a till slip, and two PDFs
that carry an image where their text layer should be — every one of them legible
at a glance. The extractor refused all four on the stated grounds that reading
them "needs a vision model", and the model behind that same extractor had been
multimodal the whole time.

So the rule these tests pin is: **a document we can turn into pixels is a
document we can read.** An image goes to the model as an image; a PDF with no
text layer is rasterized and goes the same way. `UnsupportedMediaError` is
reserved for what it always meant — a type we genuinely cannot open.

Two bounds are load-bearing and tested here rather than trusted:

* Pages are capped. A 40-page statement would otherwise put 40 images in one
  request and blow the context window, failing an invoice we could have read.
* Images are downscaled. A modern phone photo is 4000px wide; sending it whole
  spends thousands of tokens on detail a receipt does not have.
"""
from __future__ import annotations

import io

import pytest

from ai_api.documents.extractor import (
    DocumentContent,
    UnsupportedMediaError,
    document_content,
    extract_lines,
)
from ai_api.models import ExtractedInvoice, LineItem
from web_api.connectors.base import DocumentPayload


def _pdf_bytes(lines: list[str], *, pages: int = 1) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for _ in range(pages):
        y = 750
        for line in lines:
            c.drawString(100, y, line)
            y -= 20
        c.showPage()
    c.save()
    return buf.getvalue()


def _image_bytes(fmt: str = "PNG", size: tuple[int, int] = (400, 200)) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, "white")
    ImageDraw.Draw(img).text((10, 10), "FAKTURA 4711", fill="black")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _payload(content: bytes, media_type: str, filename: str = "doc") -> DocumentPayload:
    return DocumentPayload(content=content, media_type=media_type, filename=filename)


def _edges(content: DocumentContent) -> list[tuple[int, int]]:
    from PIL import Image

    return [Image.open(io.BytesIO(img.content)).size for img in content.images]


# -- Dispatch ----------------------------------------------------------------


def test_a_pdf_with_a_text_layer_still_goes_to_the_text_path():
    """The cheap path stays the default: pixels cost tokens that text does not."""
    content = document_content(_payload(_pdf_bytes(["Acme Corp"]), "application/pdf"))

    assert content.text is not None and "Acme Corp" in content.text
    assert content.images == ()


@pytest.mark.parametrize(
    "fmt, media_type",
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")],
)
def test_a_photographed_receipt_becomes_an_image_to_look_at(fmt, media_type):
    content = document_content(_payload(_image_bytes(fmt), media_type, "receipt"))

    assert content.text is None
    assert len(content.images) == 1


def test_a_pdf_with_no_text_layer_is_rasterized_rather_than_refused():
    """The scan-in-a-PDF case: valid, parseable, and empty of text."""
    content = document_content(_payload(_pdf_bytes([]), "application/pdf"))

    assert content.text is None
    assert len(content.images) == 1, "the page itself is the document"


def test_a_charset_suffix_does_not_defeat_the_image_dispatch():
    content = document_content(
        _payload(_image_bytes(), "image/png; charset=binary", "receipt.png")
    )

    assert len(content.images) == 1


def test_a_type_we_genuinely_cannot_open_is_still_unsupported():
    with pytest.raises(UnsupportedMediaError) as exc:
        document_content(_payload(b"whatever", "application/zip", "books.zip"))

    assert "application/zip" in str(exc.value)
    assert "books.zip" in str(exc.value)


def test_a_corrupt_image_reports_its_media_type_not_a_decoder_traceback():
    """Blameless-input rule: the failure must name the document, not our stack."""
    with pytest.raises(UnsupportedMediaError) as exc:
        document_content(_payload(b"\x89PNG\r\n\x1a\n truncated", "image/png", "bad.png"))

    assert "bad.png" in str(exc.value)


# -- Bounds ------------------------------------------------------------------


def test_a_long_document_is_capped_at_the_page_limit(monkeypatch):
    from ai_api import config

    monkeypatch.setattr(config, "DOC_VISION_MAX_PAGES", 3)
    content = document_content(_payload(_pdf_bytes([], pages=10), "application/pdf"))

    assert len(content.images) == 3


def test_a_phone_sized_photo_is_downscaled(monkeypatch):
    from ai_api import config

    monkeypatch.setattr(config, "DOC_VISION_MAX_EDGE", 800)
    content = document_content(_payload(_image_bytes(size=(4000, 3000)), "image/jpeg"))

    assert max(_edges(content)[0]) == 800


def test_an_image_already_below_the_limit_is_not_upscaled(monkeypatch):
    from ai_api import config

    monkeypatch.setattr(config, "DOC_VISION_MAX_EDGE", 2000)
    content = document_content(_payload(_image_bytes(size=(400, 200)), "image/png"))

    assert _edges(content)[0] == (400, 200)


# -- Extraction --------------------------------------------------------------


def test_an_image_is_extracted_by_looking_at_it():
    payload = _payload(_image_bytes(), "image/png", "receipt.png")
    seen: list[tuple[str, tuple]] = []

    def _look(prompt: str, images) -> ExtractedInvoice:
        seen.append((prompt, tuple(images)))
        return ExtractedInvoice(
            vendor_name="Acme", currency="DKK", total=120.5,
            line_items=[LineItem(description="Kaffe", amount=120.5)],
        )

    def _kickoff(prompt: str) -> ExtractedInvoice:
        raise AssertionError("an image must never reach the text extractor")

    result = extract_lines(payload, kickoff=_kickoff, look=_look)

    assert [l.description for l in result.lines] == ["Kaffe"]
    assert len(seen[0][1]) == 1, "the image itself must reach the model"


def test_a_text_pdf_never_reaches_the_vision_path():
    payload = _payload(_pdf_bytes(["INVOICE", "Monitor 3200"]), "application/pdf")

    def _look(prompt: str, images) -> ExtractedInvoice:
        raise AssertionError("a readable PDF must not be rasterized")

    def _kickoff(prompt: str) -> ExtractedInvoice:
        return ExtractedInvoice(
            vendor_name="Acme", currency="DKK", total=3200.0,
            line_items=[LineItem(description="Monitor", amount=3200.0)],
        )

    result = extract_lines(payload, kickoff=_kickoff, look=_look)

    assert [l.description for l in result.lines] == ["Monitor"]


def test_the_vision_path_reports_the_same_shape_as_the_text_path():
    """Downstream cannot tell how a line was read, and must not need to."""
    payload = _payload(_image_bytes(), "image/png")

    def _look(prompt: str, images) -> ExtractedInvoice:
        return ExtractedInvoice(
            vendor_name="Acme", currency="EUR", invoice_number=" IN-9 ",
            total=90.0, line_items=[LineItem(description="Sub", amount=90.0)],
        )

    result = extract_lines(payload, look=_look)

    assert result.currency == "EUR"
    assert result.invoice_number == "IN-9", "a printed number is stripped, as on the text path"
