"""Per-invoice render style + extra fields, built deterministically from a seeded Faker."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta

from faker import Faker

_ACCENT_PALETTE = [
    "#2b6cb0",
    "#276749",
    "#c05621",
    "#6b46c1",
    "#b7791f",
    "#2c7a7b",
    "#9b2335",
    "#1a365d",
]

_FONT_STACKS = [
    "'Helvetica Neue', Helvetica, Arial, sans-serif",
    "'Times New Roman', Times, serif",
    "'Georgia', 'Palatino Linotype', Palatino, serif",
    "'Courier New', Courier, monospace",
]

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%B %d, %Y",
    "%d %b %Y",
]

_NUMBER_FORMATS = [
    "comma",
    "period",
    "space",
]

_PAYMENT_TERMS = ["Net 15", "Net 30", "Net 45", "Net 60", "Due on Receipt", "EOM"]

_EU_BANKS = [
    "Deutsche Bank", "BNP Paribas", "ING Bank", "Nordea Bank",
    "Société Générale", "ABN AMRO", "Rabobank", "Commerzbank",
    "Handelsbanken", "Danske Bank",
]

_EU_COUNTRY_IBAN_PREFIX = {
    "DE": ("DE", 22),
    "FR": ("FR", 27),
    "NL": ("NL", 18),
    "DK": ("DK", 18),
}


@dataclass
class RenderStyle:
    accent: str
    font_stack: str
    show_logo: bool
    monogram: str
    date_format: str
    number_format: str


@dataclass
class RenderSpec:
    template_name: str
    style: RenderStyle
    vendor_address: str
    buyer_address: str
    po_number: str | None
    payment_terms: str
    due_date: str
    bank_name: str | None
    iban: str | None
    notes: str | None


def _monogram(name: str) -> str:
    """Return up to 3 uppercase initials from the vendor name words."""
    words = [w for w in name.split() if w.isalpha()]
    initials = "".join(w[0].upper() for w in words[:3])
    return initials or name[:2].upper()


def _fake_iban(fake: Faker, country_code: str) -> str:
    prefix, length = _EU_COUNTRY_IBAN_PREFIX.get(country_code, ("EU", 20))
    digits_needed = length - len(prefix) - 2
    digits = fake.numerify("#" * digits_needed)
    check = fake.numerify("##")
    return f"{prefix}{check}{digits}"


def _add_net_days(date_str: str, terms: str) -> str:
    """Derive due date from invoice_date + net days in payment_terms."""
    try:
        base = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str

    net_days = 30
    for word in terms.split():
        if word.isdigit():
            net_days = int(word)
            break
    if "Receipt" in terms:
        net_days = 0
    if "EOM" in terms:
        last_day = calendar.monthrange(base.year, base.month)[1]
        return base.replace(day=last_day).strftime("%Y-%m-%d")

    due = base + timedelta(days=net_days)
    return due.strftime("%Y-%m-%d")


def build_render_spec(
    faker: Faker,
    *,
    vendor_name: str,
    buyer_name: str,
    invoice_date: str,
    vat_regime: str,
    available_templates: list[str],
) -> RenderSpec:
    """Build a deterministic RenderSpec from the passed seeded faker."""
    template_name = faker.random_element(available_templates)

    style = RenderStyle(
        accent=faker.random_element(_ACCENT_PALETTE),
        font_stack=faker.random_element(_FONT_STACKS),
        show_logo=faker.boolean(chance_of_getting_true=60),
        monogram=_monogram(vendor_name),
        date_format=faker.random_element(_DATE_FORMATS),
        number_format=faker.random_element(_NUMBER_FORMATS),
    )

    payment_terms = faker.random_element(_PAYMENT_TERMS)
    due_date = _add_net_days(invoice_date, payment_terms)

    if vat_regime == "EU":
        supplier_cc = faker.random_element(sorted(_EU_COUNTRY_IBAN_PREFIX.keys()))
        bank_name: str | None = faker.random_element(_EU_BANKS)
        iban: str | None = _fake_iban(faker, supplier_cc)
    else:
        bank_name = None
        iban = None

    po_number: str | None = (
        f"PO-{faker.numerify('######')}" if faker.boolean(chance_of_getting_true=60) else None
    )

    notes_options = [
        "Please quote invoice number with payment.",
        "Late payment subject to 2% monthly interest.",
        "All prices in agreed contract currency.",
        "Thank you for your business.",
        None,
    ]
    notes: str | None = faker.random_element(notes_options)

    return RenderSpec(
        template_name=template_name,
        style=style,
        vendor_address=faker.address().replace("\n", ", "),
        buyer_address=faker.address().replace("\n", ", "),
        po_number=po_number,
        payment_terms=payment_terms,
        due_date=due_date,
        bank_name=bank_name,
        iban=iban,
        notes=notes,
    )
