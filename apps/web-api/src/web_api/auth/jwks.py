"""A cached JSON Web Key Set fetched over HTTP."""
from __future__ import annotations

import threading
from typing import Callable

import httpx
import jwt

from .principal import TokenVerificationError


class JwksCache:
    """Fetches a JWKS over HTTP, caches keys by ``kid``, refreshes on a miss."""

    def __init__(self, jwks_url: str, http_get: Callable[[str], dict] | None = None) -> None:
        self._url = jwks_url
        self._http_get = http_get or self._default_get
        self._keys: dict[str, "jwt.PyJWK"] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _default_get(url: str) -> dict:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _load(self) -> None:
        data = self._http_get(self._url)
        keys: dict[str, jwt.PyJWK] = {}
        for entry in data.get("keys", []):
            kid = entry.get("kid")
            if kid:
                keys[kid] = jwt.PyJWK.from_dict(entry)
        with self._lock:
            self._keys = keys

    def get_key(self, kid: str) -> "jwt.PyJWK":
        with self._lock:
            key = self._keys.get(kid)
        if key is None:
            self._load()
            with self._lock:
                key = self._keys.get(kid)
        if key is None:
            raise TokenVerificationError(f"unknown signing key '{kid}'")
        return key
