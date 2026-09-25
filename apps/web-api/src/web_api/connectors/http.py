"""Shared HTTP plumbing for ERP connectors."""
from __future__ import annotations

import logging
import re
import time
from abc import abstractmethod
from typing import Any

import httpx

from .base import (
    ErpAuthError,
    ErpConnectionError,
    ErpConnector,
    ErpDataError,
    ErpRateLimitError,
)
from .pagination import PageNumberPaginator, Paginator

logger = logging.getLogger(__name__)

_FILENAME_RE = re.compile(r'filename="?([^";]+)"?')


class HttpErpConnector(ErpConnector):
    """Base for connectors that reach their ERP over HTTP."""

    paginator: Paginator = PageNumberPaginator()

    timeout: float = 30.0

    max_retries: int = 2

    retry_backoff_seconds: float = 0.5

    def __init__(self, config: dict, http_client: httpx.Client | None = None) -> None:
        super().__init__(config)
        self._http = http_client

    @abstractmethod
    def _auth_headers(self) -> dict[str, str]:
        """Headers that authenticate one request, evaluated per request."""

    def _base_url(self) -> str:
        """The ERP's API root."""
        return ""

    def _http_client(self) -> httpx.Client:
        """The shared client, built on first use."""
        if self._http is None:
            self._http = httpx.Client(base_url=self._base_url(), timeout=self.timeout)
        return self._http

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        """The ERP's requested delay in seconds, if it named one we understand."""
        raw = response.headers.get("retry-after")
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Translate a non-2xx response into the connector error vocabulary."""
        status = response.status_code
        if status < 300:
            return
        if status in (401, 403):
            raise ErpAuthError(f"Auth failed ({status}): {response.text}")
        if status == 429:
            raise ErpRateLimitError(
                f"Rate limited: {response.text}", retry_after=self._retry_after(response)
            )
        if status >= 500:
            raise ErpConnectionError(f"ERP error {status}: {response.text}")
        raise ErpDataError(f"Unexpected {status}: {response.text}")

    def _request(
        self,
        path: str,
        *,
        authenticated: bool = True,
        **params: Any,
    ) -> httpx.Response:
        """One GET, with bounded retry on rate limits and server errors."""
        headers = self._auth_headers() if authenticated else {}
        query = params or None
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                response = self._http_client().get(path, headers=headers, params=query)
            except httpx.RequestError as exc:
                raise ErpConnectionError(str(exc)) from exc

            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == attempts - 1:
                self._raise_for_status(response)
                return response

            delay = self._retry_after(response)
            if delay is None:
                delay = self.retry_backoff_seconds * (2**attempt)
            logger.info(
                "ERP answered %s; retrying in %.2fs (attempt %d/%d)",
                response.status_code, delay, attempt + 1, attempts,
            )
            if delay > 0:
                time.sleep(delay)
            headers = self._auth_headers() if authenticated else {}

        raise ErpConnectionError("Exhausted retries without a response")

    def _get(self, path: str, **params: Any) -> dict:
        """GET a JSON resource."""
        response = self._request(path, **params)
        try:
            return response.json()
        except ValueError as exc:
            raise ErpDataError(f"Malformed JSON from {path}: {exc}") from exc

    def _paginate(
        self, path: str, *, items_key: str | None = None, **params: Any
    ) -> list[dict]:
        """Every item from a list endpoint, following this ERP's paging."""
        return self.paginator.collect(self._get, path, params, items_key)

    def _request_raw(
        self, path: str, *, authenticated: bool = True
    ) -> tuple[bytes, str | None] | None:
        """GET a non-JSON resource."""
        headers = self._auth_headers() if authenticated else {}
        try:
            response = self._http_client().get(path, headers=headers)
        except httpx.RequestError as exc:
            raise ErpConnectionError(str(exc)) from exc

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ErpConnectionError(
                f"ERP error {response.status_code}: {response.text}"
            )

        filename = None
        disposition = response.headers.get("content-disposition")
        if disposition:
            match = _FILENAME_RE.search(disposition)
            if match:
                filename = match.group(1)
        return response.content, filename
