"""Pagination strategies for HTTP ERP connectors."""
from .next_link import NextLinkPaginator
from .page_number import PageNumberPaginator
from .paginator import MAX_PAGES, Fetch, Paginator
from .skip_pages import SkipPagesPaginator

__all__ = [
    "MAX_PAGES",
    "Fetch",
    "NextLinkPaginator",
    "PageNumberPaginator",
    "Paginator",
    "SkipPagesPaginator",
]
