"""Turn a document into pictures a vision model can read."""
from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass

import pypdfium2 as pdfium
from PIL import Image, UnidentifiedImageError

from .. import config

logger = logging.getLogger("ai_api.documents")


@dataclass(frozen=True)
class DocumentImage:
    """One picture of a document, ready to send."""

    media_type: str
    content: bytes


IMAGE_MEDIA_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/tiff",
}


class ImageDecodeError(Exception):
    """The bytes did not open as a picture."""


def _encode(image, *, prefer_png: bool) -> DocumentImage:
    """Serialize a Pillow image, choosing the format its content deserves."""
    buf = io.BytesIO()
    if prefer_png or "A" in image.getbands():
        image.save(buf, format="PNG", optimize=True)
        return DocumentImage(media_type="image/png", content=buf.getvalue())
    image.convert("RGB").save(buf, format="JPEG", quality=90, optimize=True)
    return DocumentImage(media_type="image/jpeg", content=buf.getvalue())


def image_from_bytes(content: bytes) -> DocumentImage:
    """One picture, downscaled to the configured bound."""
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageDecodeError(str(exc)) from exc

    prefer_png = (image.format or "").upper() == "PNG"
    max_edge = config.DOC_VISION_MAX_EDGE
    if max(image.size) > max_edge:
        image.thumbnail((max_edge, max_edge), Image.LANCZOS)
    return _encode(image, prefer_png=prefer_png)


def pdf_page_images(content: bytes) -> list[DocumentImage]:
    """Render a PDF's pages as bands, bounded, each at the configured long edge."""
    max_edge = config.DOC_VISION_MAX_EDGE
    bands = max(1, config.DOC_VISION_PAGE_BANDS)
    max_images = max(1, config.DOC_VISION_MAX_IMAGES)

    pdf = pdfium.PdfDocument(io.BytesIO(content))
    try:
        total_pages = len(pdf)
        wanted = min(total_pages, config.DOC_VISION_MAX_PAGES)
        images: list[DocumentImage] = []

        for index in range(wanted):
            if len(images) >= max_images:
                break
            page = pdf[index]
            longest = max(page.get_size()) or 1
            rendered = page.render(scale=(max_edge * bands) / longest).to_pil()
            width, height = rendered.size
            step = height / bands
            for band in range(bands):
                if len(images) >= max_images:
                    break
                top = int(round(band * step))
                bottom = height if band == bands - 1 else int(round((band + 1) * step))
                images.append(_encode(rendered.crop((0, top, width, bottom)), prefer_png=True))

        covered = math.ceil(len(images) / bands)
        if covered < total_pages:
            logger.warning(
                "vision: reading %d of %d page(s) — capped at %d image(s) "
                "(%d band(s) per page); the rest of the document is not read",
                covered, total_pages, max_images, bands,
            )
        return images
    finally:
        pdf.close()
