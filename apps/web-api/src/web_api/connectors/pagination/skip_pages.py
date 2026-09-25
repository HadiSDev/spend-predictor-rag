"""Skip-count pagination driven by a next-page marker."""
from __future__ import annotations

from typing import Sequence

from .paginator import MAX_PAGES, Fetch, Paginator, dig_path


class SkipPagesPaginator(Paginator):
    """Skip-count paging where the response points at the next page."""

    def __init__(
        self,
        *,
        items_key: str = "collection",
        next_path: Sequence[str] = ("pagination", "nextPage"),
        skip_param: str = "skippages",
        size_param: str = "pagesize",
        page_size: int = 100,
    ) -> None:
        self.items_key = items_key
        self.next_path = tuple(next_path)
        self.skip_param = skip_param
        self.size_param = size_param
        self.page_size = page_size

    def collect(
        self, fetch: Fetch, path: str, params: dict, items_key: str | None = None
    ) -> list[dict]:
        key = items_key or self.items_key
        items: list[dict] = []
        skipped = 0
        for _ in range(MAX_PAGES):
            body = fetch(
                path,
                **{self.skip_param: skipped, self.size_param: self.page_size},
                **params,
            )
            batch = body.get(key) or []
            items.extend(batch)
            if not batch or not dig_path(body, self.next_path):
                break
            skipped += 1
        return items
