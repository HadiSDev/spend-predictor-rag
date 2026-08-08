"""The outbound seam for daily reference rates.

One method, one shape: fetch every EUR-based rate published for a date. The
narrowness is the point — it is what lets tests inject a stub and what keeps the
rest of the FX code free of HTTP concerns. It is not an invitation to build a
provider registry.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol, runtime_checkable

import httpx

from .. import config

logger = logging.getLogger(__name__)

# What a fetch returns: the publication date actually served, and every
# EUR→quote rate published for it.
RateSet = tuple[date, dict[str, Decimal]]


@runtime_checkable
class RateProvider(Protocol):
    """Fetches the full set of EUR-based reference rates for one date."""

    def fetch(self, rate_date: date) -> RateSet | None:
        """Return ``(served_date, {quote_currency: rate_per_eur})``, or None.

        `served_date` is the publication the source actually answered with,
        which is **not** always `rate_date`: reference rates are published on
        business days only, so a weekend or holiday resolves back to the prior
        publication. Callers store the served date, so a converted row records
        the rate date it truly used.

        Returns None when no rate could be obtained, for any reason. Failure is
        a value here, not an exception: an unreachable rate source must never
        take down the ingestion path that calls it.
        """
        ...


class NullProvider:
    """The disabled provider: never fetches, always returns None.

    Used whenever `FX_ENABLED` is off, which is the default — so a test run or
    an offline sync makes no outbound request and simply leaves rows
    unconverted.
    """

    def fetch(self, rate_date: date) -> RateSet | None:
        return None


class FrankfurterProvider:
    """ECB daily reference rates via the Frankfurter API (free, no API key).

    A non-publication date is answered by the API with the prior publication and
    the `date` field of the response says which one — so backward resolution
    costs no extra request and needs no calendar of our own.
    """

    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or config.FX_PROVIDER_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else config.FX_HTTP_TIMEOUT_SECONDS

    def fetch(self, rate_date: date) -> RateSet | None:
        url = f"{self.base_url}/{rate_date.isoformat()}"
        try:
            # Redirects are followed: the service has moved host once already
            # (api.frankfurter.app -> api.frankfurter.dev/v1), and a 301 that
            # silently reads as "no rate" would leave everything unconverted
            # with nothing but a log line to say why.
            response = httpx.get(
                url, params={"from": "EUR"}, timeout=self.timeout, follow_redirects=True
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # network, HTTP status, or malformed JSON
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

        # The source quotes EUR against the others but does not list EUR itself.
        rates.setdefault("EUR", Decimal(1))
        return served, rates


def default_provider() -> RateProvider:
    """The provider the application uses, per configuration."""
    return FrankfurterProvider() if config.FX_ENABLED else NullProvider()
