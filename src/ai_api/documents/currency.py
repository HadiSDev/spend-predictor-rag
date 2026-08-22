"""Put an extraction and its ledger posting into one currency before judging them.

Anthropic bills in EUR, Cloudflare in USD, EK Waterblocks in EUR — all three
posted to a Danish ledger in DKK. Reconciliation compared the document's own
figures against the ledger's total with no regard for that, so a correctly read
EUR 62.11 credit memo was rejected for not summing to DKK 464.24. Those
documents could never be accepted however well they were read, and the failure
they recorded — "the extracted lines do not reconcile" — pointed at the
extraction rather than at the currency.

The rule here is **compare like with like, or say why you cannot**. The lines
are converted into the invoice's currency at the rate in force on the invoice's
own date — the same rule every stored amount in this system already follows,
never today's rate — and only then judged. When no rate can be had, the
extraction is refused with a reason that names the mismatch, which is a true
statement where "the lines do not add up" was not.

**This converts a sum, for a comparison, and nothing else.** No converted figure
is stored: :func:`~ai_api.documents.replace.replace_invoice_lines` still writes
the document's own amounts as the evidence they are, and
``POST /companies/{id}/recompute-fx`` remains the only thing that writes base
figures. Applying one rate to a total is approximate, which is exactly why it
feeds a tolerance check and never a ledger row.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

logger = logging.getLogger("ai_api.documents")

#: Symbols with exactly one reading, mapped to their ISO code. A document prints
#: what it prints, and the model reports it: a real reply gave `€` where the
#: prompt asked for `EUR`, which compared as a mismatch between a currency and
#: itself and refused a document already in the invoice's own currency.
#:
#: Deliberately excludes the ambiguous ones. A bare `$` is a dozen currencies and
#: `kr` is DKK, NOK, SEK or ISK; guessing either compares at a confidently wrong
#: rate, which is worse than not comparing at all.
_SYMBOLS = {
    "€": "EUR",
    "£": "GBP",
    "US$": "USD",
    "USD$": "USD",
    "CA$": "CAD",
    "A$": "AUD",
    "NZ$": "NZD",
    "R$": "BRL",
    "₹": "INR",
    "₺": "TRY",
    "₽": "RUB",
    "₩": "KRW",
    "₪": "ILS",
    "DKR": "DKK",
    "SKR": "SEK",
    "NKR": "NOK",
}


def _code(written: str | None) -> str | None:
    """The ISO code a currency was written as, or ``None`` if we cannot tell.

    ``None`` means "unstated", which the caller compares at face value — the
    behaviour that preceded any currency check. It never means "assume the
    invoice's own", which would silently accept a foreign-currency document.
    """
    text = (written or "").strip().rstrip(".").strip().upper()
    if not text:
        return None
    if len(text) == 3 and text.isalpha():
        return text
    return _SYMBOLS.get(text)


_ONE = Decimal("1")


def conversion_rate(
    document_currency: str | None,
    invoice_currency: str | None,
    on_date: date | None,
    fx,
) -> tuple[Decimal | None, str | None]:
    """What one unit of the document's money is worth in the invoice's.

    Returns ``(rate, None)`` or ``(None, reason)``. A document in the invoice's
    own currency — or naming none — converts at exactly ``1`` rather than
    ``None``, so a caller can multiply unconditionally; a ``None`` that has to
    be special-cased at every call site is a crash waiting for the one site that
    forgets.

    **Never defaults to 1 when a rate is genuinely missing**, because that is
    precisely the bug this exists to prevent: it stores a foreign figure in a
    local column, and an EUR 18.80 line reads as DKK 18.80 forever after.
    """
    document = _code(document_currency)
    invoice = _code(invoice_currency)

    if document is None or invoice is None or document == invoice:
        return _ONE, None

    resolved = fx.get_rate(document, invoice, on_date)
    if resolved is None:
        return None, (
            f"the document is in {document} but the invoice is posted in "
            f"{invoice}, and no {document}→{invoice} rate is available for "
            f"{on_date or 'an unknown date'}, so the two cannot be compared"
        )

    rate, published = resolved
    logger.info(
        "  document is in %s, invoice in %s: converting at %s (rate of %s)",
        document, invoice, rate, published,
    )
    return rate, None


def comparable_total(
    lines_total: Decimal,
    document_currency: str | None,
    invoice_currency: str | None,
    on_date: date | None,
    fx,
) -> tuple[Decimal | None, str | None]:
    """``lines_total`` restated in the invoice's currency.

    Returns ``(total, None)`` when the comparison can be made, and
    ``(None, reason)`` when it cannot. ``fx`` is anything with ``get_rate``;
    :class:`~web_api.fx.service.FxService` is what the runner passes and a stub
    is what the tests do.

    A document that states **no** currency is taken at face value. Most state
    one, and treating silence as a mismatch would reject every extraction off a
    receipt that simply never printed a code — trading a real problem for a
    larger invented one. The same applies when the *invoice* names no currency:
    there is nothing to convert to.
    """
    rate, reason = conversion_rate(document_currency, invoice_currency, on_date, fx)
    if rate is None:
        return None, reason
    # The same rate the caller stores the lines at — one decision, so the figure
    # judged and the figure written can never disagree.
    return lines_total * rate, None
