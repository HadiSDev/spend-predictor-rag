"""Invoice generation for the mock ERP."""

from __future__ import annotations

import itertools
import random
from datetime import date, timedelta

from .accounts import account_name
from .seeding import seeded_random
from .vendors import VENDOR_SPECS

ACCOUNT_DESCRIPTIONS: dict[int, list[str]] = {
    6010: [
        "Cloud server - monthly hosting",
        "CDN bandwidth usage",
        "Database instance - production",
        "Object storage - monthly fee",
        "Load balancer - hourly rate",
    ],
    6015: [
        "API usage - monthly subscription",
        "Data feed license",
        "Model inference credits",
        "Third-party integration fee",
    ],
    6020: [
        "SaaS license - monthly seat",
        "Software annual renewal",
        "Collaboration tool subscription",
        "Dev tool license",
    ],
    6030: [
        "Mobile data plan - monthly",
        "Internet fiber - business",
        "SIP trunking - monthly",
        "Conference call service",
    ],
    6500: [
        "Printer paper - bulk pack",
        "Office stationery - monthly",
        "Toner cartridge replacement",
        "Desk accessories",
    ],
    6510: [
        "Standing desk - 1 unit",
        "Office chair replacement",
        "Monitor 27in - 2 units",
        "Meeting room screen",
    ],
    6600: [
        "Management consulting - hourly",
        "Strategy workshop - full day",
        "Due diligence support",
        "Interim CFO services",
    ],
    6610: [
        "Legal retainer - monthly",
        "Contract review - fixed fee",
        "IP filing - legal services",
        "Compliance advisory",
    ],
    6620: [
        "Monthly bookkeeping",
        "Annual audit preparation",
        "Tax filing assistance",
        "Accounting software integration",
    ],
    6700: [
        "Social media campaign - monthly",
        "Google Ads - managed spend",
        "Content creation - blog posts",
        "SEO optimization - quarterly",
    ],
    6800: [
        "Copenhagen to London - round trip",
        "Stockholm business trip - airfare",
        "Berlin conference - flight",
        "Oslo meeting - airfare",
    ],
    6810: [
        "Hotel - 3 nights business",
        "Airbnb - 5 nights",
        "Conference hotel - 2 nights",
        "Corporate apartment - monthly",
    ],
    6820: [
        "Client dinner - 4 persons",
        "Team lunch - monthly",
        "Business meeting catering",
        "Christmas party - venue",
    ],
    6900: [
        "Electricity - monthly consumption",
        "Water & waste - quarterly",
        "Gas heating - monthly",
        "Building maintenance fee",
    ],
    6910: [
        "Office rent - monthly",
        "Parking spaces - monthly",
        "Storage unit rental",
        "Meeting room rental - daily",
    ],
    7000: [
        "Package delivery - domestic",
        "Freight - EU standard",
        "Courier - express",
        "Pallet shipping",
    ],
    7050: [
        "Developer contractor - hourly",
        "Designer freelance - project",
        "QA engineer - hourly",
        "Data entry - temp staff",
    ],
    7100: [
        "Online course - per seat",
        "Conference ticket",
        "Team training - full day",
        "Certification exam fee",
    ],
}


def _pick_lines(
    rng: random.Random,
    vendor: dict,
    account_number: int,
    month_offset: int,
    is_cheaper: bool,
) -> list[dict]:
    """Generate 1-3 invoice lines for one invoice."""
    descriptions = ACCOUNT_DESCRIPTIONS.get(account_number, ["Service fee"])
    lines: list[dict] = []
    n_lines = rng.randint(1, 3)
    for li in range(n_lines):
        desc = rng.choice(descriptions)
        if month_offset > 0:
            desc = f"{desc} (M{month_offset})"
        base_price = rng.uniform(500, 15000)
        if is_cheaper:
            base_price *= 0.85
        qty = rng.choice([1, 1, 1, 2, 3, 5, 10, 20])
        unit_price = round(base_price / qty, 2)
        net_amount = round(qty * unit_price, 2)
        lines.append({
            "lineNumber": li + 1,
            "description": desc,
            "quantity": qty,
            "unitPrice": unit_price,
            "netAmount": net_amount,
            "account": {
                "accountNumber": account_number,
                "name": account_name(account_number),
            },
            "vatRate": 25.0,
        })
    return lines


def _account_for_vendor(vendor: dict) -> int:
    """Pick the primary expense account for a vendor based on type."""
    group = vendor.get("supplier_group", "")
    group_to_account = {
        "IT Services": 6010,
        "Software": 6020,
        "Office Supplies": 6500,
        "Consulting": 6600,
        "Marketing": 6700,
        "Logistics": 7000,
        "Legal": 6610,
        "Accounting": 6620,
        "Travel": 6800,
        "Property": 6910,
        "Facilities": 6510,
        "Telecom": 6030,
        "Utilities": 6900,
        "Staffing": 7050,
        "Education": 7100,
    }
    return group_to_account.get(group, 6600)


def generate(
    seed: int = 42,
    n_months: int = 12,
    avg_invoices_per_month: int = 15,
    start_date: date | None = None,
) -> list[dict]:
    """Generate invoices for the mock ERP."""
    rng = seeded_random(seed)
    if start_date is None:
        start_date = date(2025, 7, 1)

    invoices: list[dict] = []
    invoice_numbers = itertools.count(1001)
    voucher_numbers = itertools.count(5001)

    for month_offset in range(n_months):
        month_date = date(
            start_date.year + (start_date.month + month_offset - 1) // 12,
            (start_date.month + month_offset - 1) % 12 + 1,
            1,
        )
        n_invoices = rng.randint(
            max(5, avg_invoices_per_month - 5),
            avg_invoices_per_month + 5,
        )
        eligible = [
            v for v in VENDOR_SPECS
            if not v.is_cheaper_alternative
        ]
        vendors_this_month = rng.choices(eligible, k=n_invoices)

        for v in vendors_this_month:
            invoice_number = next(invoice_numbers)
            voucher = next(voucher_numbers)
            inv_date = month_date + timedelta(days=rng.randint(0, 27))
            if inv_date > date(2026, 12, 31):
                inv_date = date(2026, 12, 31)

            account_number = _account_for_vendor(vars(v))
            is_cheap = False
            lines = _pick_lines(rng, vars(v), account_number, month_offset, is_cheap)
            net = sum(ln["netAmount"] for ln in lines)
            vat = round(net * 0.25, 2)
            gross = round(net + vat, 2)

            invoices.append({
                "purchaseInvoiceNumber": invoice_number,
                "voucherId": voucher,
                "file": {
                    "fileName": f"invoice_{invoice_number}.pdf",
                    "fileRef": f"scans/{voucher}/invoice_{invoice_number}.pdf",
                },
                "supplier": {
                    "supplierNumber": v.vendorNumber,
                    "name": v.name,
                },
                "date": inv_date.isoformat(),
                "currency": v.currency,
                "grossAmount": gross,
                "netAmount": net,
                "vatAmount": vat,
                "lines": lines,
            })

    return invoices
