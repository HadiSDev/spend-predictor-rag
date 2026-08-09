"""Shared HTTP plumbing for ERP connectors.

Every connector we will write talks HTTP to a REST API, and the parts that are
genuinely the same for all of them — building the client, turning a status code
into one of our four errors, backing off when rate-limited, pulling bytes for a
document — live here so they exist once rather than once per ERP.

What differs stays with the connector, behind two small seams:

* ``_auth_headers()`` — the headers that authenticate a request.
* ``paginator`` — how this ERP's lists are paged (see ``pagination.py``).

``_auth_headers()`` is called **per request**, not once at ``authorize()``.
That is deliberate and it is the whole reason this is a hook rather than a
stored header dict: Business Central's bearer token expires, so its connector
will refresh inside this hook and nothing above it — not ``ErpConnector``, not
the sync runner — has to learn that tokens can expire.
"""
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

    #: How this ERP pages its list endpoints. Subclasses override.
    paginator: Paginator = PageNumberPaginator()

    #: Seconds before a single request is abandoned.
    timeout: float = 30.0

    #: Extra attempts after the first for a retryable response (429, 5xx).
    #: Zero disables retrying.
    max_retries: int = 2

    #: Base delay for exponential backoff. Tests set this to 0 so a retry path
    #: costs no wall-clock time.
    retry_backoff_seconds: float = 0.5

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        #: Public by convention: tests assign an ``httpx.Client`` (often a
        #: ``TestClient`` bound to an ASGI app) here to serve requests without a
        #: live server and without patching httpx internals.
        self._http: httpx.Client | None = None

    # -- Seams subclasses fill ----------------------------------------------

    @abstractmethod
    def _auth_headers(self) -> dict[str, str]:
        """Headers that authenticate one request, evaluated per request."""

    def _base_url(self) -> str:
        """The ERP's API root. Subclasses that take a configurable host override."""
        return ""

    # -- Client --------------------------------------------------------------

    def _http_client(self) -> httpx.Client:
        """The shared client, built on first use.

        Built lazily so constructing a connector opens no socket — the catalog
        endpoint instantiates connectors just to read their class attributes.
        """
        if self._http is None:
            self._http = httpx.Client(base_url=self._base_url(), timeout=self.timeout)
        return self._http

    # -- Error mapping -------------------------------------------------------

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        """The ERP's requested delay in seconds, if it named one we understand.

        ``Retry-After`` may also be an HTTP date; we do not parse that, and
        ``None`` simply means "back off on our own schedule".
        """
        raw = response.headers.get("retry-after")
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Translate a non-2xx response into the connector error vocabulary.

        One place, so a caller's ``except ErpAuthError`` means the same thing
        whichever ERP raised it.
        """
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

    # -- Requests ------------------------------------------------------------

    def _request(
        self,
        path: str,
        *,
        authenticated: bool = True,
        **params: Any,
    ) -> httpx.Response:
        """One GET, with bounded retry on rate limits and server errors.

        Only 429 and 5xx are retried. A transport failure is not: an unreachable
        host does not become reachable by asking again inside one sync, and the
        runner already isolates the failure to this integration.

        ``authenticated=False`` sends no auth headers — used for a document
        stored on a host that is not the ERP, where sending the credential would
        hand it to a third party.
        """
        headers = self._auth_headers() if authenticated else {}
        # httpx *replaces* a URL's query string when given params, so passing an
        # empty dict would strip the query off an absolute cursor link and send
        # us back to page one forever. No params means send the URL as given.
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
            # Re-evaluated deliberately: a token may have expired mid-retry.
            headers = self._auth_headers() if authenticated else {}

        # Unreachable: the final attempt either returns or raises above.
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
        """Every item from a list endpoint, following this ERP's paging.

        ``items_key`` names the response key holding the rows, for an ERP that
        keys each list by its resource name rather than uniformly.
        """
        return self.paginator.collect(self._get, path, params, items_key)

    def _request_raw(
        self, path: str, *, authenticated: bool = True
    ) -> tuple[bytes, str | None] | None:
        """GET a non-JSON resource. Returns ``(content, filename)``.

        ``None`` on a 404 — nothing at this path, an ordinary case for a voucher
        with no document. Any other failure raises ``ErpConnectionError``, so a
        caller can tell "nothing there" from "couldn't reach the ERP".
        """
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
