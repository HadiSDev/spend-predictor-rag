"""Currency parsing, vendored from `groundley-ai/packages/parsers`."""
from enum import Enum
from typing import Optional


class CurrencyCode(str, Enum):
    """ISO 4217 currency codes"""

    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CHF = "CHF"

    CNY = "CNY"
    INR = "INR"
    KRW = "KRW"
    SGD = "SGD"
    HKD = "HKD"
    AUD = "AUD"
    NZD = "NZD"
    THB = "THB"
    MYR = "MYR"
    PHP = "PHP"
    IDR = "IDR"
    VND = "VND"
    TWD = "TWD"

    CAD = "CAD"
    BRL = "BRL"
    MXN = "MXN"
    ARS = "ARS"
    CLP = "CLP"
    COP = "COP"
    PEN = "PEN"

    DKK = "DKK"
    SEK = "SEK"
    NOK = "NOK"
    PLN = "PLN"
    CZK = "CZK"
    HUF = "HUF"
    RON = "RON"
    BGN = "BGN"
    HRK = "HRK"
    ISK = "ISK"
    RUB = "RUB"
    TRY = "TRY"
    UAH = "UAH"

    ILS = "ILS"
    AED = "AED"
    SAR = "SAR"
    QAR = "QAR"
    KWD = "KWD"
    EGP = "EGP"
    ZAR = "ZAR"


def parse_currency(value: str) -> Optional[CurrencyCode]:
    """Parse currency symbols and codes to ISO 4217 format."""
    currency_str = str(value).strip()

    if not currency_str:
        return None

    currency_upper = currency_str.upper()

    try:
        return CurrencyCode(currency_upper)
    except ValueError:
        pass

    clear_symbol_map = {
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
        "€": "EUR",
        "£": "GBP",
        "₹": "INR",
        "₽": "RUB",
        "₩": "KRW",
        "₪": "ILS",
        "฿": "THB",
        "₺": "TRY",
        "zł": "PLN",
        "ZŁ": "PLN",
        "Fr.": "CHF",
        "SFr.": "CHF",
    }

    mapped_currency = clear_symbol_map.get(currency_str)
    if not mapped_currency:
        mapped_currency = clear_symbol_map.get(currency_upper)

    if mapped_currency:
        return CurrencyCode(mapped_currency)

    return None
