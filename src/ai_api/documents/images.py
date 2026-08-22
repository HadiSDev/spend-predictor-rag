"""Turn a document into pictures a vision model can read.

Exists because half the dev org's unread invoices are not broken documents: a
PNG screenshot of a subscription receipt, a JPEG photo of a till slip, and two
PDFs carrying an image where their text layer should be. Every one is legible at
a glance, and the extractor refused all four on the grounds that reading them
needed a vision model — which the deployment had been serving the whole time.

Two bounds are applied here rather than trusted to the caller:

* **Pages are capped** (:data:`~ai_api.config.DOC_VISION_MAX_PAGES`). Each page
  is an image and each image is thousands of tokens, so a long statement would
  overflow the context window and fail a document we could have read.
* **Pixels are capped** (:data:`~ai_api.config.DOC_VISION_MAX_EDGE`). A phone
  photo is ~4000px on its long edge and a receipt carries no detail at that
  size, but the encoder charges for it. PDF pages are *rendered* at the target
  size rather than rendered large and shrunk — same result, none of the work.

Both are read off the config module at call time, never bound at import, so they
can be moved without a restart's worth of ceremony.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from .. import config


@dataclass(frozen=True)
class DocumentImage:
    """One picture of a document, ready to send.

    Carries its own media type because the two producers here disagree on
    purpose: a rendered page and a screenshot stay PNG so their text stays
    crisp, while a photograph becomes JPEG rather than a multi-megabyte
    lossless copy of camera noise.
    """

    media_type: str
    content: bytes


#: Formats Pillow can open and the model can look at. Membership is checked on
#: the declared type; the bytes still have to open, and a type that opens
#: nothing is an unsupported document, not a crash.
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
    """One picture, downscaled to the configured bound.

    Raises :class:`ImageDecodeError` when the bytes do not open — the caller
    turns that into a failure that names the document rather than the decoder.
    """
    from PIL import Image, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageDecodeError(str(exc)) from exc

    # A screenshot is mostly text and stays lossless; a photograph does not.
    prefer_png = (image.format or "").upper() == "PNG"
    max_edge = config.DOC_VISION_MAX_EDGE
    if max(image.size) > max_edge:
        # `thumbnail` preserves the aspect ratio and never upscales, which is
        # the whole contract: a small screenshot must come back untouched.
        image.thumbnail((max_edge, max_edge), Image.LANCZOS)
    return _encode(image, prefer_png=prefer_png)


def pdf_page_images(content: bytes) -> list[DocumentImage]:
    """Render a PDF's pages, capped, each at the configured long edge.

    The scale is computed per page from that page's own point size, so a page
    lands on the bound rather than near it, and an A3 page does not arrive at
    twice the resolution of the A4 one beside it.
    """
    import pypdfium2 as pdfium

    max_edge = config.DOC_VISION_MAX_EDGE
    pdf = pdfium.PdfDocument(io.BytesIO(content))
    try:
        pages: list[DocumentImage] = []
        for index in range(min(len(pdf), config.DOC_VISION_MAX_PAGES)):
            page = pdf[index]
            longest = max(page.get_size()) or 1
            rendered = page.render(scale=max_edge / longest).to_pil()
            pages.append(_encode(rendered, prefer_png=True))
        return pages
    finally:
        pdf.close()
