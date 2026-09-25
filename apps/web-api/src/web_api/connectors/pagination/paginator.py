"""The paging contract every HTTP connector's list walk follows."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Sequence


Fetch = Callable[..., dict]
MAX_PAGES = 1000


def dig_path(body: dict, path: Sequence[str]) -> Any:
    """Follow a nested key path, returning ``None`` if any step is missing."""
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
        """All items from ``path``, following pages until the ERP stops."""
