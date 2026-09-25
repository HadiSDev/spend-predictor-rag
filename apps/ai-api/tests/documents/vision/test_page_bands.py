"""Give the model enough pixels to read a price column."""
from __future__ import annotations

import io

import pytest
from PIL import Image
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

import ai_api.config as cfg
from ai_api import config
from ai_api.documents.images import pdf_page_images


def _pdf(pages: int = 1) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for n in range(pages):
        c.drawString(100, 750, f"page {n + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _sizes(images):
    return [Image.open(io.BytesIO(i.content)).size for i in images]


def test_a_page_is_split_into_the_configured_number_of_bands(monkeypatch):
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 3)

    images = pdf_page_images(_pdf())

    assert len(images) == 3


def test_one_band_is_the_whole_page(monkeypatch):
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 1)

    images = pdf_page_images(_pdf())

    assert len(images) == 1


def test_each_band_is_rendered_at_the_configured_resolution(monkeypatch):
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 3)
    monkeypatch.setattr(config, "DOC_VISION_MAX_EDGE", 1000)

    heights = [h for _w, h in _sizes(pdf_page_images(_pdf()))]

    assert all(abs(h - 1000) <= 2 for h in heights), heights


def test_the_bands_tile_the_page_without_overlapping(monkeypatch):
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 4)
    monkeypatch.setattr(config, "DOC_VISION_MAX_EDGE", 500)

    sizes = _sizes(pdf_page_images(_pdf()))
    widths = {w for w, _h in sizes}

    assert len(widths) == 1, "every band spans the full page width"
    assert abs(sum(h for _w, h in sizes) - 2000) <= 4


def test_a_multi_page_document_bands_every_page(monkeypatch):
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 2)
    monkeypatch.setattr(config, "DOC_VISION_MAX_IMAGES", 99)
    monkeypatch.setattr(config, "DOC_VISION_MAX_PAGES", 99)

    assert len(pdf_page_images(_pdf(pages=3))) == 6


def test_the_total_number_of_images_is_capped(monkeypatch):
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 3)
    monkeypatch.setattr(config, "DOC_VISION_MAX_IMAGES", 7)
    monkeypatch.setattr(config, "DOC_VISION_MAX_PAGES", 99)

    assert len(pdf_page_images(_pdf(pages=10))) == 7


def test_what_the_cap_discards_is_logged(caplog):
    with caplog.at_level("WARNING"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cfg, "DOC_VISION_PAGE_BANDS", 2)
            mp.setattr(cfg, "DOC_VISION_MAX_IMAGES", 3)
            mp.setattr(cfg, "DOC_VISION_MAX_PAGES", 99)
            pdf_page_images(_pdf(pages=5))

    assert "cap" in caplog.text.lower() or "capped" in caplog.text.lower()


def test_the_page_cap_still_applies(monkeypatch):
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 2)
    monkeypatch.setattr(config, "DOC_VISION_MAX_PAGES", 2)
    monkeypatch.setattr(config, "DOC_VISION_MAX_IMAGES", 99)

    assert len(pdf_page_images(_pdf(pages=6))) == 4


def test_bands_never_span_two_pages(monkeypatch):
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 2)
    monkeypatch.setattr(config, "DOC_VISION_MAX_IMAGES", 99)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(100, 750, "portrait page")
    c.showPage()
    c.setPageSize(landscape(A4))
    c.drawString(100, 400, "landscape page")
    c.showPage()
    c.save()

    sizes = _sizes(pdf_page_images(buf.getvalue()))

    assert len(sizes) == 4, "two pages, two bands each"
    portrait_widths = {w for w, _h in sizes[:2]}
    landscape_widths = {w for w, _h in sizes[2:]}
    assert len(portrait_widths) == 1 and len(landscape_widths) == 1
    assert portrait_widths != landscape_widths, (
        "each band carries its own page's shape, so no band spans two pages"
    )
