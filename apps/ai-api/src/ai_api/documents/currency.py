"""Put an extraction and its ledger posting into one currency before judging them."""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from web_api.parsers.currency import parse_currency

logger = logging.getLogger("ai_api.documents")


def _code(written: str | None) -> str | None:
    """The ISO 4217 code a currency was written as, or ``None`` if we cannot tell."""
    code = parse_currency(written) if written else None
    return code.value if code is not None else None


_ONE = Decimal("1")


def conversion_rate(
    document_currency: str | None,
    invoice_currency: str | None,
    on_date: date | None,
    fx,
) -> tuple[Decimal | None, str | None]:
    """What one unit of the document's money is worth in the invoice's."""
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
    """``lines_total`` restated in the invoice's currency."""
    rate, reason = conversion_rate(document_currency, invoice_currency, on_date, fx)
    if rate is None:
        return None, reason
    return lines_total * rate, None
