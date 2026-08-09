"""Converting money into a company's base currency at a historical rate.

The rule this module exists to enforce: an amount is converted at the rate in
force on **its own transaction date**, or it is not converted at all. There is no
fallback to today's rate and no fallback to a neighbouring currency — a figure
that looks authoritative and is not would be worse than a missing one.

Rates are cached in `fx_rates` against EUR, so any pair is derived as
``rate(EUR→B) / rate(EUR→A)`` and n currencies cost n rows per date rather
than n². `FxService` adds a per-instance memo in front of that, so one date
resolves to at most one provider call per run no matter how many rows need it.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

from sqlmodel import Session, select

from ..db.models import ErpEntry, FxRate, Invoice, InvoiceLine
from .provider import RateProvider, RateSet, default_provider

logger = logging.getLogger(__name__)

EUR = "EUR"
_ONE = Decimal(1)
_RATE_SCALE = Decimal("0.00000001")  # Numeric(18, 8)
_MONEY_SCALE = Decimal("0.01")  # Numeric(14, 2)

# What happened to a row we were asked to convert. Callers report these as
# counts; nothing branches on them.
CONVERTED = "converted"
UNCONVERTED = "unconverted"
UNCHANGED = "unchanged"


def normalize_currency(code: str | None) -> str | None:
    """Uppercase a currency code, or None if it isn't one."""
    if not code:
        return None
    code = code.strip().upper()
    return code if len(code) == 3 and code.isalpha() else None


def convert(amount: Decimal | None, rate: Decimal) -> Decimal | None:
    """Apply a rate to an amount, rounded half-up to the money scale.

    Deliberately takes the *stored* (8dp) rate rather than a full-precision
    quotient: a stored base amount must be reproducible from the stored original
    amount and the stored rate, and it only is if both sides round the same way.
    """
    if amount is None:
        return None
    return (Decimal(amount) * rate).quantize(_MONEY_SCALE, rounding=ROUND_HALF_UP)


class FxService:
    """Resolves historical rates for one unit of work.

    Holds a per-instance memo, so it is meant to be created per sync run, per
    request, or per recompute — not kept alive for the life of the process.
    """

    def __init__(self, session: Session, provider: RateProvider | None = None) -> None:
        self.session = session
        self.provider = provider if provider is not None else default_provider()
        # requested date -> EUR rate set, or None when it could not be resolved.
        # The None entries matter as much as the hits: they stop a dead provider
        # from being asked once per row.
        self._memo: dict[date, Optional[tuple[date, dict[str, Decimal]]]] = {}

    # -- rates ---------------------------------------------------------------

    def get_rate(
        self, from_currency: str | None, to_currency: str | None, on_date: date | None
    ) -> tuple[Decimal, date] | None:
        """Return ``(rate, published_date)`` for ``from → to`` on ``on_date``.

        The rate is units of `to` per 1 unit of `from`, so
        ``base = amount * rate``. Returns None when the date is missing, either
        currency is missing or unknown to the rate source, or no rate could be
        obtained — the caller then leaves the row unconverted.
        """
        source = normalize_currency(from_currency)
        target = normalize_currency(to_currency)
        if source is None or target is None or on_date is None:
            return None
        if source == target:
            # No lookup needed, and none wanted: an amount already in the base
            # currency is converted at 1 on its own date.
            return _ONE, on_date

        resolved = self._eur_rates(on_date)
        if resolved is None:
            return None
        published, rates = resolved
        if source not in rates or target not in rates or not rates[source]:
            logger.warning(
                "FX: no published rate for %s→%s on %s", source, target, on_date
            )
            return None

        rate = (rates[target] / rates[source]).quantize(_RATE_SCALE, rounding=ROUND_HALF_UP)
        return rate, published

    def _eur_rates(self, on_date: date) -> tuple[date, dict[str, Decimal]] | None:
        """The EUR-based rate set for a date, from memo, then cache, then source."""
        if on_date in self._memo:
            return self._memo[on_date]

        cached = self._read_cache(on_date)
        if cached is None:
            cached = self._fetch_and_cache(on_date)
        self._memo[on_date] = cached
        return cached

    def _read_cache(self, on_date: date) -> tuple[date, dict[str, Decimal]] | None:
        rows = self.session.exec(select(FxRate).where(FxRate.rate_date == on_date)).all()
        if not rows:
            return None
        return rows[0].published_date, {r.quote_currency: r.rate for r in rows}

    def _fetch_and_cache(self, on_date: date) -> tuple[date, dict[str, Decimal]] | None:
        fetched: RateSet | None = self.provider.fetch(on_date)
        if fetched is None:
            return None
        published, rates = fetched

        # Cache under the date served and, when they differ, under the date
        # asked for — so the same weekend is answered from the cache next time
        # and still reports the publication it really came from.
        self._write_cache(on_date, published, rates)
        if published != on_date:
            self._write_cache(published, published, rates)
        return published, rates

    def _write_cache(
        self, rate_date: date, published: date, rates: dict[str, Decimal]
    ) -> None:
        existing = {
            r.quote_currency
            for r in self.session.exec(
                select(FxRate).where(FxRate.rate_date == rate_date)
            ).all()
        }
        source = type(self.provider).__name__
        for currency, rate in rates.items():
            if currency in existing:
                continue
            self.session.add(
                FxRate(
                    quote_currency=currency,
                    rate_date=rate_date,
                    published_date=published,
                    rate=rate,
                    source=source,
                )
            )

    # -- rows ----------------------------------------------------------------

    def convert_row(
        self,
        row,
        *,
        base_currency: str,
        source_currency: str | None,
        on_date: date | None,
        amount_fields: Iterable[tuple[str, str]],
    ) -> str:
        """Write a row's base amounts, rate and rate date. Returns the outcome.

        A row is left exactly as it is when its conversion is already the one we
        would write — that is what makes a re-sync free of write churn.

        "Already the one we would write" means the stored base amounts are still
        *reproducible* from the posted amounts at the stored rate, not merely
        that some rate is present. A row is upserted in place by a deterministic
        id, so its posted amounts can change under a conversion that was correct
        for the old ones; trusting the mere presence of a rate froze the base
        amounts of an earlier posting onto the new one, which then rendered as a
        figure from an unrelated row — even with the sign inverted, when the old
        posting used the other side of the ledger.
        """
        amount_fields = tuple(amount_fields)
        if (
            row.fx_rate is not None
            and row.base_currency == base_currency
            and all(
                getattr(row, base_field) == convert(getattr(row, source_field), row.fx_rate)
                for source_field, base_field in amount_fields
            )
        ):
            return UNCHANGED

        resolved = self.get_rate(source_currency, base_currency, on_date)
        if resolved is None:
            self._clear(row, amount_fields)
            return UNCONVERTED

        rate, published = resolved
        for source_field, base_field in amount_fields:
            setattr(row, base_field, convert(getattr(row, source_field), rate))
        row.base_currency = base_currency
        row.fx_rate = rate
        row.fx_rate_date = published
        return CONVERTED

    @staticmethod
    def _clear(row, amount_fields: Iterable[tuple[str, str]]) -> None:
        """Leave a row unmistakably unconverted rather than half-converted."""
        for _, base_field in amount_fields:
            setattr(row, base_field, None)
        row.base_currency = None
        row.fx_rate = None
        row.fx_rate_date = None

    # -- the three convertible shapes ---------------------------------------
    #
    # Which date and which currency each row converts at lives here and nowhere
    # else, so the runner, the recompute and any future caller cannot disagree
    # about it.

    def convert_invoice(self, invoice: Invoice, base_currency: str) -> str:
        return self.convert_row(
            invoice,
            base_currency=base_currency,
            source_currency=invoice.currency,
            on_date=invoice.invoice_date,
            amount_fields=(("total", "base_total"), ("tax", "base_tax")),
        )

    def convert_line(
        self,
        line: InvoiceLine,
        base_currency: str,
        *,
        currency: str | None,
        invoice_date: date | None,
    ) -> str:
        """A line has no date or currency of its own — both come from its invoice."""
        return self.convert_row(
            line,
            base_currency=base_currency,
            source_currency=currency,
            on_date=invoice_date,
            amount_fields=(("amount", "base_amount"),),
        )

    def convert_entry(self, entry: ErpEntry, base_currency: str) -> str:
        return self.convert_row(
            entry,
            base_currency=base_currency,
            source_currency=entry.currency,
            on_date=entry.accounting_date,
            amount_fields=(
                ("debit_amount", "base_debit_amount"),
                ("credit_amount", "base_credit_amount"),
            ),
        )
