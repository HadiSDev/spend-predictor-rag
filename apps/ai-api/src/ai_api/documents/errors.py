"""Why a document could not be read."""


class UnsupportedMediaError(Exception):
    """The document is fine; we have no extractor that can read this type."""


class EmptyDocumentError(Exception):
    """The document opened, but carries nothing to extract from."""


class VisionUnreadableError(Exception):
    """Not one page of the document produced a usable answer."""
