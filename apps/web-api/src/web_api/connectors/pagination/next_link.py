"""Cursor pagination that follows an absolute next-link."""
from __future__ import annotations

from .paginator import MAX_PAGES, Fetch, Paginator


class NextLinkPaginator(Paginator):
    """Cursor paging: follow an absolute next-link until the ERP omits it."""

    def __init__(
        self,
        *,
        items_key: str = "value",
        next_key: str = "@odata.nextLink",
    ) -> None:
        self.items_key = items_key
        self.next_key = next_key

    def collect(
        self, fetch: Fetch, path: str, params: dict, items_key: str | None = None
    ) -> list[dict]:
        key = items_key or self.items_key
        items: list[dict] = []
        body = fetch(path, **params)
        for _ in range(MAX_PAGES):
            items.extend(body.get(key) or [])
            next_link = body.get(self.next_key)
            if not next_link:
                break
            body = fetch(next_link)
        return items
