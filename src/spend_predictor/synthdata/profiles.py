"""Buyer profiles. The buyer's business decides Direct vs Indirect (level1)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuyerProfile:
    name: str
    website: str
    country_code: str
    vat_number: str
    business_description: str
    direct_level2: frozenset[str]  # chart level2 groups that are Direct for this buyer


def level1_for(profile: BuyerProfile, level2: str) -> str:
    """Direct if the account's level2 group is core to this buyer, else Indirect."""
    return "Direct" if level2 in profile.direct_level2 else "Indirect"


PROFILES: list[BuyerProfile] = [
    BuyerProfile(
        name="Nimbus Analytics A/S", website="https://nimbus.example", country_code="DK",
        vat_number="DK12345678",
        business_description="A SaaS company selling a cloud analytics platform; "
        "its cost of revenue is cloud infrastructure and third-party data APIs.",
        direct_level2=frozenset({"Technology"}),
    ),
    BuyerProfile(
        name="Meridian Legal Partners", website="https://meridian-legal.example",
        country_code="DE", vat_number="DE222222222",
        business_description="A corporate law firm; its cost of revenue is the work "
        "of its lawyers and outside professional services.",
        direct_level2=frozenset({"Professional Services"}),
    ),
    BuyerProfile(
        name="Harbor Freight Logistics Inc.", website="https://harborfreight.example",
        country_code="US", vat_number="",
        business_description="A freight and logistics company; its cost of revenue is "
        "shipping, freight and contract delivery labor.",
        direct_level2=frozenset({"Logistics", "People"}),
    ),
]
