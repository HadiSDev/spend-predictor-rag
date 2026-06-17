# src/spend_predictor/synthdata/sampler.py
"""Seeded sampler that builds InvoicePlans (all ground-truth labels, no LLM)."""
from __future__ import annotations

from dataclasses import dataclass

from faker import Faker

from ..rag.indexer import load_accounts
from .profiles import PROFILES, BuyerProfile, level1_for

_UNIT_TYPES = ["pcs", "hours", "months", "units", "GB", "licenses"]
_CURRENCIES = {"EU": ["EUR", "DKK"], "US": ["USD"]}
_EU_VAT_RATES = [25.0, 21.0, 19.0]


@dataclass
class LinePlan:
    quantity: float
    unit_type: str
    unit_price: float
    amount: float
    vat_code: str | None
    vat_rate: float | None


@dataclass
class InvoicePlan:
    buyer: BuyerProfile
    account: dict
    vat_regime: str  # "EU" | "US"
    currency: str
    vendor_name: str
    invoice_number: str
    invoice_date: str
    supplier_country_code: str | None
    supplier_vat_number: str | None
    buyer_country_code: str | None
    buyer_vat_number: str | None
    lines: list[LinePlan]
    subtotal: float
    tax: float
    total: float
    level1: str


def _sample_one(fake: Faker, account: dict, profile: BuyerProfile) -> InvoicePlan:
    regime = fake.random_element(["EU", "US"])
    currency = fake.random_element(_CURRENCIES[regime])
    vat_rate = fake.random_element(_EU_VAT_RATES) if regime == "EU" else 0.0

    n_lines = fake.random_int(1, 4)
    lines: list[LinePlan] = []
    for _ in range(n_lines):
        qty = float(fake.random_int(1, 20))
        unit_price = round(fake.random_int(500, 200000) / 100.0, 2)
        amount = round(qty * unit_price, 2)
        lines.append(LinePlan(
            quantity=qty, unit_type=fake.random_element(_UNIT_TYPES),
            unit_price=unit_price, amount=amount,
            vat_code=("S" if regime == "EU" else None),
            vat_rate=(vat_rate if regime == "EU" else None),
        ))

    subtotal = round(sum(l.amount for l in lines), 2)
    tax = round(subtotal * vat_rate / 100.0, 2)
    total = round(subtotal + tax, 2)

    supplier_cc = fake.random_element(["DE", "FR", "NL", "DK"]) if regime == "EU" else "US"
    supplier_vat = f"{supplier_cc}{fake.numerify('#########')}" if regime == "EU" else ""

    return InvoicePlan(
        buyer=profile, account=account, vat_regime=regime, currency=currency,
        vendor_name=fake.company(),
        invoice_number=fake.numerify("INV-####-####"),
        invoice_date=fake.date(pattern="%Y-%m-%d"),
        supplier_country_code=supplier_cc,
        supplier_vat_number=supplier_vat or None,
        buyer_country_code=profile.country_code or None,
        buyer_vat_number=(profile.vat_number or None) if regime == "EU" else None,
        lines=lines, subtotal=subtotal, tax=tax, total=total,
        level1=level1_for(profile, account["level2"]),
    )


def sample_plans(
    n: int, seed: int, *,
    accounts: list[dict] | None = None,
    profiles: list[BuyerProfile] | None = None,
) -> list[InvoicePlan]:
    """Return `n` deterministic InvoicePlans for the given seed."""
    accounts = accounts if accounts is not None else load_accounts()
    profiles = profiles if profiles is not None else PROFILES
    fake = Faker()
    Faker.seed(seed)
    fake.seed_instance(seed)
    return [
        _sample_one(fake, fake.random_element(accounts), fake.random_element(profiles))
        for _ in range(n)
    ]
