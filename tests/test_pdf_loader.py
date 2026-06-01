import pytest

from spend_predictor.pdf_loader import extract_text


def _make_pdf(path, lines):
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    y = 750
    for line in lines:
        c.drawString(100, y, line)
        y -= 20
    c.save()


def test_extract_text_returns_content(tmp_path):
    pdf = tmp_path / "inv.pdf"
    _make_pdf(pdf, ["INVOICE", "Acme Corp", "Total 123.45"])
    text = extract_text(pdf)
    assert "INVOICE" in text
    assert "Acme Corp" in text


def test_extract_text_empty_pdf_returns_empty(tmp_path):
    pdf = tmp_path / "blank.pdf"
    _make_pdf(pdf, [])
    assert extract_text(pdf).strip() == ""


def test_extract_text_raises_on_nonpdf(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_text("this is not a pdf")
    with pytest.raises(Exception):
        extract_text(bad)
