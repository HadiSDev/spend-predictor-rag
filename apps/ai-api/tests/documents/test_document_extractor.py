"""Reading a fetched document: media-type dispatch and reconciliation."""
from __future__ import annotations

import io
from decimal import Decimal

import pytest
from reportlab.pdfgen import canvas

from ai_api.documents.extractor import (
    EmptyDocumentError,
    ExtractedLines,
    UnsupportedMediaError,
    document_text,
    extract_lines,
)
from ai_api.documents.reconcile import reconcile, tolerance_for
from ai_api.models import ExtractedInvoice, LineItem
from web_api import config as web_config
from web_api.connectors.base import DocumentPayload


def _pdf_bytes(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 750
    for line in lines:
        c.drawString(100, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def _payload(content: bytes, media_type: str, filename: str = "inv-1.pdf") -> DocumentPayload:
    return DocumentPayload(content=content, media_type=media_type, filename=filename)


def test_a_pdf_is_read():
    payload = _payload(_pdf_bytes(["INVOICE", "Acme Corp", "Total 123.45"]), "application/pdf")

    assert "Acme Corp" in document_text(payload)


def test_a_charset_suffix_does_not_defeat_the_dispatch():
    payload = _payload(
        _pdf_bytes(["INVOICE"]), "application/pdf; charset=binary"
    )

    assert "INVOICE" in document_text(payload)


def test_a_photographed_receipt_is_not_handed_to_a_pdf_parser():
    payload = _payload(b"\xff\xd8\xff\xe0 not a pdf", "image/jpeg", filename="receipt.jpg")

    with pytest.raises(UnsupportedMediaError) as exc:
        document_text(payload)
    assert "image/jpeg" in str(exc.value)
    assert "receipt.jpg" in str(exc.value)


def test_an_unknown_media_type_is_reported_as_such():
    payload = _payload(b"whatever", "", filename="mystery.bin")

    with pytest.raises(UnsupportedMediaError) as exc:
        document_text(payload)
    assert "unknown" in str(exc.value)


def test_a_pdf_with_no_text_layer_is_its_own_failure():
    payload = _payload(_pdf_bytes([]), "application/pdf")

    with pytest.raises(EmptyDocumentError) as exc:
        document_text(payload)
    assert "vision model" in str(exc.value)


def test_extraction_returns_the_documents_lines():
    payload = _payload(_pdf_bytes(["INVOICE", "Monitor 3200"]), "application/pdf")
    seen: list[str] = []

    def _kickoff(prompt: str) -> ExtractedInvoice:
        seen.append(prompt)
        return ExtractedInvoice(
            vendor_name="Acme", currency="DKK", total=3200.0,
            line_items=[LineItem(description="Dell U2724DE monitor", amount=3200.0)],
        )

    result = extract_lines(payload, kickoff=_kickoff)

    assert isinstance(result, ExtractedLines)
    assert [l.description for l in result.lines] == ["Dell U2724DE monitor"]
    assert result.currency == "DKK"
    assert "Monitor 3200" in seen[0], "the document's own text must reach the model"


def test_the_tolerance_is_the_larger_of_relative_and_absolute(monkeypatch):
    monkeypatch.setattr(web_config, "DOC_RECONCILE_TOLERANCE_PCT", 0.01)
    monkeypatch.setattr(web_config, "DOC_RECONCILE_TOLERANCE_ABS", 1.00)

    assert tolerance_for(Decimal("50.00")) == Decimal("1.00")
    assert tolerance_for(Decimal("10000.00")) == Decimal("100.0000")


def test_lines_matching_the_gross_total_reconcile():
    assert reconcile(Decimal("1000.00"), Decimal("1000.00"), Decimal("200.00")).ok


def test_lines_matching_the_net_total_reconcile():
    assert reconcile(Decimal("800.00"), Decimal("1000.00"), Decimal("200.00")).ok


def test_a_missed_line_does_not_reconcile():
    result = reconcile(Decimal("300.00"), Decimal("1000.00"), Decimal("200.00"))

    assert not result.ok
    assert "300.00" in result.reason and "1000.00" in result.reason and "800.00" in result.reason


def test_no_total_means_nothing_to_check_against():
    result = reconcile(Decimal("7.00"), None, None)

    assert result.ok and result.checked is False


def test_no_tax_still_reconciles_against_the_gross():
    assert reconcile(Decimal("1000.00"), Decimal("1000.00"), None).ok


def test_a_credit_note_reconciles_on_its_own_sign():
    assert reconcile(Decimal("-1000.00"), Decimal("-1000.00"), None).ok
