"""Vendored from `groundley-ai/packages/parsers`, unchanged.

Adopted rather than reimplemented after a hand-rolled parser in this repo kept
getting real invoices wrong: `5.780 kr.` refused as ambiguous when the ledger
beside it said 5780, `31.12.99` at risk of reading as 31.12, and a 13-digit
EKWB article number accepted as a line total. This one analyses a figure's
groups and separators instead of matching a handful of shapes.

**Kept verbatim.** Local needs are handled by the callers that wrap it —
`ai_api/documents/numbers.py` normalizes a U+2212 minus before calling, because
that is our documents' quirk and not this parser's business. Editing the file
would fork it from upstream and make the next update a merge.
"""
from enum import Enum
from typing import Optional


class CurrencyCode(str, Enum):
    """ISO 4217 currency codes"""

    # Major currencies
    USD = "USD"  # US Dollar
    EUR = "EUR"  # Euro
    GBP = "GBP"  # British Pound
    JPY = "JPY"  # Japanese Yen
    CHF = "CHF"  # Swiss Franc

    # Asia Pacific
    CNY = "CNY"  # Chinese Yuan
    INR = "INR"  # Indian Rupee
    KRW = "KRW"  # South Korean Won
    SGD = "SGD"  # Singapore Dollar
    HKD = "HKD"  # Hong Kong Dollar
    AUD = "AUD"  # Australian Dollar
    NZD = "NZD"  # New Zealand Dollar
    THB = "THB"  # Thai Baht
    MYR = "MYR"  # Malaysian Ringgit
    PHP = "PHP"  # Philippine Peso
    IDR = "IDR"  # Indonesian Rupiah
    VND = "VND"  # Vietnamese Dong
    TWD = "TWD"  # Taiwan Dollar

    # Americas
    CAD = "CAD"  # Canadian Dollar
    BRL = "BRL"  # Brazilian Real
    MXN = "MXN"  # Mexican Peso
    ARS = "ARS"  # Argentine Peso
    CLP = "CLP"  # Chilean Peso
    COP = "COP"  # Colombian Peso
    PEN = "PEN"  # Peruvian Sol

    # Europe
    DKK = "DKK"  # Danish Krone
    SEK = "SEK"  # Swedish Krona
    NOK = "NOK"  # Norwegian Krone
    PLN = "PLN"  # Polish Zloty
    CZK = "CZK"  # Czech Koruna
    HUF = "HUF"  # Hungarian Forint
    RON = "RON"  # Romanian Leu
    BGN = "BGN"  # Bulgarian Lev
    HRK = "HRK"  # Croatian Kuna
    ISK = "ISK"  # Icelandic Krona
    RUB = "RUB"  # Russian Ruble
    TRY = "TRY"  # Turkish Lira
    UAH = "UAH"  # Ukrainian Hryvnia

    # Middle East & Africa
    ILS = "ILS"  # Israeli Shekel
    AED = "AED"  # UAE Dirham
    SAR = "SAR"  # Saudi Riyal
    QAR = "QAR"  # Qatari Riyal
    KWD = "KWD"  # Kuwaiti Dinar
    EGP = "EGP"  # Egyptian Pound
    ZAR = "ZAR"  # South African Rand


def parse_currency(value: str) -> Optional[CurrencyCode]:
    """
    Parse currency symbols and codes to ISO 4217 format.

    Rules:
    - Returns UNKNOWN if value is None or empty
    - Returns UNKNOWN for ambiguous symbols (kr, ¥, R, etc.)
    - Converts clear currency symbols to ISO codes ($→USD, €→EUR, £→GBP)
    - Validates 3-letter codes against known ISO 4217 codes
    - Returns UNKNOWN for invalid/unknown currency codes
    """
    currency_str = str(value).strip()

    # if none or empty, return None
    if not currency_str or len(currency_str) == 0:
        return None

    currency_upper = currency_str.upper()

    # Try to create the enum directly
    try:
        return CurrencyCode(currency_upper)
    except ValueError:
        pass

    # Unambiguous currency symbol to ISO 4217 code mapping
    clear_symbol_map = {
        # Dollar variants with clear prefixes
        "$": "USD",
        "US$": "USD",
        "A$": "AUD",
        "AU$": "AUD",
        "C$": "CAD",
        "CA$": "CAD",
        "NZ$": "NZD",
        "S$": "SGD",
        "SG$": "SGD",
        "HK$": "HKD",
        "MX$": "MXN",
        "R$": "BRL",
        # Euro
        "€": "EUR",
        # Pound
        "£": "GBP",
        # Clear single-currency symbols
        "₹": "INR",
        "₽": "RUB",
        "₩": "KRW",
        "₪": "ILS",
        "฿": "THB",
        "₺": "TRY",
        "zł": "PLN",
        "ZŁ": "PLN",
        # Swiss Franc with period
        "Fr.": "CHF",
        "SFr.": "CHF",
    }

    # Check for clear symbol mapping
    mapped_currency = clear_symbol_map.get(currency_str)
    if not mapped_currency:
        mapped_currency = clear_symbol_map.get(currency_upper)

    if mapped_currency:
        return CurrencyCode(mapped_currency)

    # Ambiguous or unknown format - return None
    return None
