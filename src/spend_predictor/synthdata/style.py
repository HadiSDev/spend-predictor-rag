# src/spend_predictor/synthdata/style.py
"""Per-invoice render style + extra fields, built deterministically from a seeded Faker."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faker import Faker

# ---------------------------------------------------------------------------
# Palette / font options
# ---------------------------------------------------------------------------
_ACCENT_PALETTE = [
    "#2b6cb0",  # steel blue
    "#276749",  # forest green
    "#c05621",  # burnt orange
    "#6b46c1",  # deep purple
    "#b7791f",  # amber
    "#2c7a7b",  # teal
    "#9b2335",  # crimson
    "#1a365d",  # navy
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
    "comma",   # 1,234.56
    "period",  # 1.234,56  (European style)
    "space",   # 1 234.56
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


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RenderStyle:
    accent: str          # hex color
    font_stack: str      # CSS font-family string
    show_logo: bool
    monogram: str        # vendor initials (2–3 chars)
    date_format: str     # strftime pattern
    number_format: str   # "comma" | "period" | "space"


@dataclass
class RenderSpec:
    template_name: str
    style: RenderStyle
    # Extra fields — render-only distractors
    vendor_address: str
    buyer_address: str
    po_number: str | None
    payment_terms: str
    due_date: str
    bank_name: str | None
    iban: str | None
    notes: str | None


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _monogram(name: str) -> str:
    """Return up to 3 uppercase initials from the vendor name words."""
    words = [w for w in name.split() if w.isalpha()]
    initials = "".join(w[0].upper() for w in words[:3])
    return initials or name[:2].upper()


def _fake_iban(fake: "Faker", country_code: str) -> str:
    prefix, length = _EU_COUNTRY_IBAN_PREFIX.get(country_code, ("EU", 20))
    digits_needed = length - len(prefix) - 2  # 2 check digits
    digits = fake.numerify("#" * digits_needed)
    check = fake.numerify("##")
    return f"{prefix}{check}{digits}"


def _add_net_days(date_str: str, terms: str) -> str:
    """Derive due date from invoice_date + net days in payment_terms."""
    try:
        base = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str  # fallback: return as-is

    net_days = 30  # default
    for word in terms.split():
        if word.isdigit():
            net_days = int(word)
            break
    if "Receipt" in terms:
        net_days = 0
    if "EOM" in terms:
        # End of current month
        if base.month == 12:
            due = base.replace(year=base.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            due = base.replace(month=base.month + 1, day=1) - timedelta(days=1)
        return due.strftime("%Y-%m-%d")

    due = base + timedelta(days=net_days)
    return due.strftime("%Y-%m-%d")


def build_render_spec(
    faker: "Faker",
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

    # IBAN / bank only for EU regime
    if vat_regime == "EU":
        # pick a supplier country from the EU pool deterministically
        supplier_cc = faker.random_element(list(_EU_COUNTRY_IBAN_PREFIX.keys()))
        bank_name: str | None = faker.random_element(_EU_BANKS)
        iban: str | None = _fake_iban(faker, supplier_cc)
    else:
        bank_name = None
        iban = None

    # PO number ~60 % of the time
    po_number: str | None = (
        f"PO-{faker.numerify('######')}" if faker.boolean(chance_of_getting_true=60) else None
    )

    # Notes ~40 % of the time
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
