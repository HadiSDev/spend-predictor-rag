"""Pagination strategies for HTTP ERP connectors.

Every ERP pages its lists, and no two page them the same way. Billy counts
pages, e-conomic counts pages it has skipped and tells you the next one,
Business Central hands back an OData cursor. That is the whole of the
difference, so it lives here as three small strategies a connector *declares*
rather than as three copies of a `while True` loop in three mappers.

A connector sets ``paginator = ...`` and calls ``self._paginate(path)``; the
shared base in ``http.py`` drives whichever strategy it finds.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Sequence

#: ``fetch(path_or_url, **params) -> body``. The base supplies this, so a
#: paginator never touches HTTP itself and is testable with a plain function.
Fetch = Callable[..., dict]

#: How many pages any strategy will walk before giving up. A server that keeps
#: promising another page would otherwise spin forever; this turns that into a
#: bounded, noisy failure instead of a hung sync.
MAX_PAGES = 1000


def _dig(body: dict, path: Sequence[str]) -> Any:
    """Follow a nested key path, returning ``None`` if any step is missing.

    ERPs bury paging metadata at different depths (``pagination.total``,
    ``meta.paging.total``), and a missing key is an ordinary "no more pages"
    signal rather than an error, so this never raises.
    """
    current: Any = body
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


class Paginator(ABC):
    """Walks one ERP's list endpoint and returns every item across its pages."""

    @abstractmethod
    def collect(
        self, fetch: Fetch, path: str, params: dict, items_key: str | None = None
    ) -> list[dict]:
        """All items from ``path``, following pages until the ERP stops.

        ``items_key`` overrides the strategy's default for one call. Some ERPs
        key every list payload the same way; Billy keys each by its resource
        name, so the caller names it per endpoint.
        """


class PageNumberPaginator(Paginator):
    """Numbered pages, with the response reporting a grand total.

    Used by Billy and by the Debug ERP. Stops once the accumulated item count
    reaches the reported total — or, if the ERP reports no total at all, once a
    page comes back empty.
    """

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
            total = _dig(body, self.total_path)
            if total is None:
                # No total to compare against, so an empty page is the only
                # honest end-of-list signal.
                if not batch:
                    break
            elif len(items) >= total:
                break
            elif not batch:
                # The total says there is more but the ERP sent nothing. Stop
                # rather than request the same empty page forever.
                break
            page += 1
        return items


class SkipPagesPaginator(Paginator):
    """Skip-count paging where the response points at the next page.

    e-conomic's shape: ask for a page by how many you have skipped, and follow
    ``pagination.nextPage`` until it is absent.
    """

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
            if not batch or not _dig(body, self.next_path):
                break
            skipped += 1
        return items


class NextLinkPaginator(Paginator):
    """Cursor paging: follow an absolute next-link until the ERP omits it.

    Business Central's OData shape. The link is opaque and already carries the
    query string, so subsequent requests send no params of their own.
    """

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
            # Opaque and self-contained: passing params again would duplicate
            # or contradict what the ERP already encoded in the link.
            body = fetch(next_link)
        return items
