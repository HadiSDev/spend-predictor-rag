"""The outbound seam for daily reference rates."""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol, runtime_checkable

import httpx

from .. import config

logger = logging.getLogger(__name__)

RateSet = tuple[date, dict[str, Decimal]]


@runtime_checkable
class RateProvider(Protocol):
    """Fetches the full set of EUR-based reference rates for one date."""

    def fetch(self, rate_date: date) -> RateSet | None:
        """Return ``(served_date, {quote_currency: rate_per_eur})``, or None."""
        ...


class NullProvider:
    """The disabled provider: never fetches, always returns None."""

    def fetch(self, rate_date: date) -> RateSet | None:
        return None


class FrankfurterProvider:
    """ECB daily reference rates via the Frankfurter API (free, no API key)."""

    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or config.FX_PROVIDER_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else config.FX_HTTP_TIMEOUT_SECONDS

    def fetch(self, rate_date: date) -> RateSet | None:
        url = f"{self.base_url}/{rate_date.isoformat()}"
        try:
            response = httpx.get(
                url, params={"from": "EUR"}, timeout=self.timeout, follow_redirects=True
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("FX: rate fetch for %s failed: %s", rate_date, exc)
            return None

        try:
            served = date.fromisoformat(payload["date"])
            rates = {
                str(ccy).upper(): Decimal(str(value))
                for ccy, value in payload["rates"].items()
            }
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            logger.warning("FX: unexpected rate payload for %s: %s", rate_date, exc)
            return None

        if not rates:
            logger.warning("FX: rate source returned no rates for %s", rate_date)
            return None

        rates.setdefault("EUR", Decimal(1))
        return served, rates


def default_provider() -> RateProvider:
    """The provider the application uses, per configuration."""
    return FrankfurterProvider() if config.FX_ENABLED else NullProvider()
