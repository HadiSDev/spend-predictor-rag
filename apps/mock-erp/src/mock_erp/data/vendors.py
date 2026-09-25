"""Vendor generation for the mock ERP, including planted redundant pairs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VendorSpec:
    vendorNumber: int
    name: str
    country: str
    vatNumber: str
    currency: str
    supplier_group: str
    category_level_2: str
    is_cheaper_alternative: bool = False


VENDOR_SPECS: list[VendorSpec] = [
    VendorSpec(1, "NordicCloud Solutions ApS", "DK", "DK12345678", "DKK", "IT Services", "Technology", is_cheaper_alternative=True),
    VendorSpec(2, "SkyNet Hosting AB", "SE", "SE87654321", "SEK", "IT Services", "Technology"),
    VendorSpec(3, "DataVault Cloud GmbH", "DE", "DE11223344", "EUR", "IT Services", "Technology"),
    VendorSpec(4, "SaaSify Nordic A/S", "DK", "DK99887766", "DKK", "Software", "Technology"),
    VendorSpec(5, "SubscripCo Ltd", "GB", "GB44556677", "GBP", "Software", "Technology"),
    VendorSpec(6, "OfficeMax Denmark", "DK", "DK55443322", "DKK", "Office Supplies", "Facilities & Office", is_cheaper_alternative=True),
    VendorSpec(7, "Paper & Pixel ApS", "DK", "DK22334455", "DKK", "Office Supplies", "Facilities & Office"),
    VendorSpec(8, "McKinsey & Co Nordic", "DK", "DK66778899", "DKK", "Consulting", "Professional Services"),
    VendorSpec(9, "Bain Nordic Partners", "DK", "DK99881122", "DKK", "Consulting", "Professional Services", is_cheaper_alternative=True),
    VendorSpec(10, "AdVenture Media A/S", "DK", "DK11223344", "DKK", "Marketing", "Sales & Marketing"),
    VendorSpec(11, "GrowthHackers ApS", "DK", "DK55667788", "DKK", "Marketing", "Sales & Marketing", is_cheaper_alternative=True),
    VendorSpec(12, "DSV Logistics A/S", "DK", "DK33445566", "DKK", "Logistics", "Logistics"),
    VendorSpec(13, "PostNord Denmark", "DK", "DK77889900", "DKK", "Logistics", "Logistics", is_cheaper_alternative=True),
    VendorSpec(14, "Gorrissen Federspiel", "DK", "DK11112222", "DKK", "Legal", "Professional Services"),
    VendorSpec(15, "Kromann Reumert", "DK", "DK33334444", "DKK", "Legal", "Professional Services"),
    VendorSpec(16, "Deloitte Denmark", "DK", "DK55556666", "DKK", "Accounting", "Professional Services"),
    VendorSpec(17, "SAS Business Travel", "DK", "DK77778888", "DKK", "Travel", "Travel & Entertainment"),
    VendorSpec(18, "CPH Airport Services", "DK", "DK99990000", "DKK", "Travel", "Travel & Entertainment"),
    VendorSpec(19, "Matrikel 1 A/S", "DK", "DK12121212", "DKK", "Property", "Facilities & Office"),
    VendorSpec(20, "ISS Facility Services", "DK", "DK34343434", "DKK", "Facilities", "Facilities & Office"),
    VendorSpec(21, "TDC Erhverv A/S", "DK", "DK56565656", "DKK", "Telecom", "Technology"),
    VendorSpec(22, "Telenor Business", "NO", "NO78787878", "NOK", "Telecom", "Technology"),
    VendorSpec(23, "Ørsted Business", "DK", "DK90909090", "DKK", "Utilities", "Facilities & Office"),
    VendorSpec(24, "Københavns Energi", "DK", "DK13131313", "DKK", "Utilities", "Facilities & Office"),
    VendorSpec(25, "HiredBy ApS", "DK", "DK57575757", "DKK", "Staffing", "People"),
    VendorSpec(26, "Upwork Global", "US", "", "USD", "Staffing", "People"),
    VendorSpec(27, "LinkedIn Learning", "US", "", "USD", "Education", "People"),
    VendorSpec(28, "Coursera Business", "US", "", "USD", "Education", "People"),
    VendorSpec(29, "AWS Europe", "IE", "IE99887766", "EUR", "IT Services", "Technology"),
    VendorSpec(30, "Azure Danmark", "DK", "DK77665544", "DKK", "IT Services", "Technology"),
]


def build_vendors() -> list[dict]:
    return [vars(s) for s in VENDOR_SPECS]


def get_cheaper_alternatives() -> dict[int, int]:
    """Map expensive vendorNumber → cheaper vendorNumber for redundant pairs."""
    result: dict[int, int] = {}
    specs_by_group: dict[str, list[VendorSpec]] = {}
    for s in VENDOR_SPECS:
        specs_by_group.setdefault(s.category_level_2, []).append(s)

    for group in specs_by_group.values():
        cheap = next((s for s in group if s.is_cheaper_alternative), None)
        if cheap is None:
            continue
        for spec in group:
            if not spec.is_cheaper_alternative and spec.supplier_group == cheap.supplier_group:
                result[spec.vendorNumber] = cheap.vendorNumber
    return result
