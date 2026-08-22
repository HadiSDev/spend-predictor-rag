"""Give the model enough pixels to read a price column.

An EKWB credit memo — clean, machine-generated, legible at a glance — came back
with null amounts every time. Not a layout the model could not parse: a page it
was shown at too few pixels. Rendered whole at a 1600px long edge, its table
occupies a thin band and its prices are a handful of pixels tall.

Rendering the same page at 3x and splitting it into three bands, the band
holding the table read perfectly::

    EK-CryoFuel Clear (Premix 1000mL)      EUR 18.80
    EK-CryoFuel Loop Cleaner + Superflush  EUR 31.41
    Shipping                               EUR 11.90

which sums to the document's own EUR 62.11 and reconciles against its DKK 464.24
posting. Two bands was tried first and was not enough — it found the two items
but missed the shipping line, leaving the sum 12 short. Three is the number that
worked, not the number that sounded right.

The cost is real and bounded here: 3x on each edge is 9x the pixels, and a
vision encoder charges for every one. So the number of images per document is
capped, and what the cap discards is logged rather than silently dropped.

The seam is the accepted risk. Bands do not overlap, so a row straddling a
boundary is cut in half and may be misread or lost. Overlapping instead would
duplicate it, and a duplicated line inflates an invoice's total — a silent wrong
number, where a lost one is caught by reconciliation.
"""
from __future__ import annotations

import io

import pytest

from ai_api import config
from ai_api.documents.images import pdf_page_images


def _pdf(pages: int = 1) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for n in range(pages):
        c.drawString(100, 750, f"page {n + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _sizes(images):
    from PIL import Image

    return [Image.open(io.BytesIO(i.content)).size for i in images]


def test_a_page_is_split_into_the_configured_number_of_bands(monkeypatch):
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 3)

    images = pdf_page_images(_pdf())

    assert len(images) == 3


def test_one_band_is_the_whole_page(monkeypatch):
    """The pre-banding behaviour stays reachable, and stays exactly one image."""
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 1)

    images = pdf_page_images(_pdf())

    assert len(images) == 1


def test_each_band_is_rendered_at_the_configured_resolution(monkeypatch):
    """The point of banding: every band gets the full pixel budget, so the page
    as a whole is rendered at bands x that."""
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 3)
    monkeypatch.setattr(config, "DOC_VISION_MAX_EDGE", 1000)

    heights = [h for _w, h in _sizes(pdf_page_images(_pdf()))]

    assert all(abs(h - 1000) <= 2 for h in heights), heights


def test_the_bands_tile_the_page_without_overlapping(monkeypatch):
    """No overlap, so nothing can be read twice and inflate a total.

    The whole page must still be covered: a gap would drop a line silently.
    """
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 4)
    monkeypatch.setattr(config, "DOC_VISION_MAX_EDGE", 500)

    sizes = _sizes(pdf_page_images(_pdf()))
    widths = {w for w, _h in sizes}

    assert len(widths) == 1, "every band spans the full page width"
    # 4 bands of ~500 tall reconstruct the 2000px render they were cut from.
    assert abs(sum(h for _w, h in sizes) - 2000) <= 4


def test_a_multi_page_document_bands_every_page(monkeypatch):
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 2)
    monkeypatch.setattr(config, "DOC_VISION_MAX_IMAGES", 99)
    monkeypatch.setattr(config, "DOC_VISION_MAX_PAGES", 99)

    assert len(pdf_page_images(_pdf(pages=3))) == 6


def test_the_total_number_of_images_is_capped(monkeypatch):
    """9x the pixels per page makes an unbounded document genuinely expensive."""
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 3)
    monkeypatch.setattr(config, "DOC_VISION_MAX_IMAGES", 7)
    monkeypatch.setattr(config, "DOC_VISION_MAX_PAGES", 99)

    assert len(pdf_page_images(_pdf(pages=10))) == 7


def test_what_the_cap_discards_is_logged(caplog):
    """A silent truncation reads as 'we covered the whole document'."""
    import ai_api.config as cfg

    with caplog.at_level("WARNING"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cfg, "DOC_VISION_PAGE_BANDS", 2)
            mp.setattr(cfg, "DOC_VISION_MAX_IMAGES", 3)
            mp.setattr(cfg, "DOC_VISION_MAX_PAGES", 99)
            pdf_page_images(_pdf(pages=5))

    assert "cap" in caplog.text.lower() or "capped" in caplog.text.lower()


def test_the_page_cap_still_applies(monkeypatch):
    """Both bounds hold; whichever bites first wins."""
    monkeypatch.setattr(config, "DOC_VISION_PAGE_BANDS", 2)
    monkeypatch.setattr(config, "DOC_VISION_MAX_PAGES", 2)
    monkeypatch.setattr(config, "DOC_VISION_MAX_IMAGES", 99)

    assert len(pdf_page_images(_pdf(pages=6))) == 4


def test_bands_never_span_two_pages(monkeypatch):
    """Pages are read individually — a band is always a slice of one page.

    Proven by giving the document two pages of *different shapes*: every band
    inherits the width of the page it was cut from, so two distinct widths in
    the output means the bands were never stitched across the page boundary.
    A merged render would produce one width for everything.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

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
