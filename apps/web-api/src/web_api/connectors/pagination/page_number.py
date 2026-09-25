"""Numbered-page pagination with a reported grand total."""
from __future__ import annotations

from typing import Sequence

from .paginator import MAX_PAGES, Fetch, Paginator, dig_path


class PageNumberPaginator(Paginator):
    """Numbered pages, with the response reporting a grand total."""

    def __init__(
        self,
        *,
        items_key: str = "collection",
        total_path: Sequence[str] = ("pagination", "total"),
        page_param: str = "page",
        size_param: str = "pageSize",
        page_size: int = 100,
        first_page: int = 1,
    ) -> None:
        self.items_key = items_key
        self.total_path = tuple(total_path)
        self.page_param = page_param
        self.size_param = size_param
        self.page_size = page_size
        self.first_page = first_page

    def collect(
        self, fetch: Fetch, path: str, params: dict, items_key: str | None = None
    ) -> list[dict]:
        key = items_key or self.items_key
        items: list[dict] = []
        page = self.first_page
        for _ in range(MAX_PAGES):
            body = fetch(
                path,
                **{self.page_param: page, self.size_param: self.page_size},
                **params,
            )
            batch = body.get(key) or []
            items.extend(batch)
            total = dig_path(body, self.total_path)
            if total is None:
                if not batch:
                    break
            elif len(items) >= total:
                break
            elif not batch:
                break
            page += 1
        return items
