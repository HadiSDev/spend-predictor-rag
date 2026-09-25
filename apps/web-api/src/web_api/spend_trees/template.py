"""The platform's default spend-tree template."""
from __future__ import annotations

from dataclasses import dataclass, field


TEMPLATE_VERSION = "2"

TEMPLATE_NAME = "Default spend tree"
TEMPLATE_MAX_DEPTH = 3


@dataclass(frozen=True)
class TemplateNode:
    """One node of the template, addressed by its full path from the root."""

    path: tuple[str, ...]
    code: str | None = None
    description: str | None = None
    keywords: frozenset[str] = field(default_factory=frozenset)

    @property
    def depth(self) -> int:
        return len(self.path)

    @property
    def name(self) -> str:
        return self.path[-1]


def _leaf(path: tuple[str, ...], code: str, description: str, keywords: set[str]) -> TemplateNode:
    return TemplateNode(path=path, code=code, description=description, keywords=frozenset(keywords))


DEFAULT_TEMPLATE: tuple[TemplateNode, ...] = (
    TemplateNode(("Direct",), description="Spend that goes into what the company sells"),
    TemplateNode(("Direct", "Direct Costs")),
    _leaf(
        ("Direct", "Direct Costs", "Cost of Goods Sold"), "4000",
        "Raw materials, components and production inputs",
        {"raw", "materials", "goods", "cogs", "production", "components"},
    ),

    TemplateNode(("Indirect",), description="Spend that runs the company"),

    TemplateNode(("Indirect", "Technology")),
    _leaf(
        ("Indirect", "Technology", "Cloud Infrastructure"), "6010",
        "Cloud hosting, compute, storage and bandwidth",
        {"cloud", "server", "hosting", "cdn", "bandwidth", "database", "instance",
         "storage", "object", "load", "balancer", "compute"},
    ),
    _leaf(
        ("Indirect", "Technology", "APIs & Data"), "6015",
        "Third-party APIs, data feeds and model inference",
        {"api", "feed", "model", "inference", "integration", "credits", "third-party"},
    ),
    _leaf(
        ("Indirect", "Technology", "Software"), "6020",
        "Software subscriptions and per-seat licences",
        {"saas", "license", "software", "subscription", "collaboration", "dev",
         "tool", "seat", "renewal"},
    ),
    _leaf(
        ("Indirect", "Technology", "Telecom"), "6030",
        "Mobile plans, internet lines and telephony",
        {"mobile", "plan", "internet", "fiber", "sip", "trunking", "telecom",
         "call", "phone"},
    ),

    TemplateNode(("Indirect", "Facilities & Office")),
    _leaf(
        ("Indirect", "Facilities & Office", "Office Supplies"), "6500",
        "Consumables: paper, stationery, toner",
        {"paper", "stationery", "toner", "cartridge", "printer", "supplies", "accessories"},
    ),
    _leaf(
        ("Indirect", "Facilities & Office", "Office Equipment"), "6510",
        "Desks, chairs, monitors and other durable office equipment",
        {"desk", "chair", "monitor", "screen", "equipment", "standing"},
    ),
    _leaf(
        ("Indirect", "Facilities & Office", "Utilities"), "6900",
        "Electricity, water, heating, waste and building maintenance",
        {"electricity", "water", "waste", "gas", "heating", "building",
         "maintenance", "utilities"},
    ),
    _leaf(
        ("Indirect", "Facilities & Office", "Rent & Lease"), "6910",
        "Office rent, parking and equipment leases",
        {"rent", "parking", "lease", "rental", "office"},
    ),

    TemplateNode(("Indirect", "Professional Services")),
    _leaf(
        ("Indirect", "Professional Services", "Consulting"), "6600",
        "Strategy, management and interim consulting",
        {"consulting", "strategy", "workshop", "diligence", "cfo", "management", "interim"},
    ),
    _leaf(
        ("Indirect", "Professional Services", "Legal"), "6610",
        "Legal retainers, contracts, IP and compliance advice",
        {"legal", "retainer", "contract", "ip", "filing", "compliance", "advisory"},
    ),
    _leaf(
        ("Indirect", "Professional Services", "Accounting"), "6620",
        "Bookkeeping, audit and tax work",
        {"bookkeeping", "audit", "tax", "accounting"},
    ),

    TemplateNode(("Indirect", "Sales & Marketing")),
    _leaf(
        ("Indirect", "Sales & Marketing", "Marketing"), "6700",
        "Advertising, campaigns, content and SEO",
        {"social", "media", "campaign", "ads", "google", "content", "blog", "seo",
         "marketing", "advertising"},
    ),

    TemplateNode(("Indirect", "Travel & Entertainment")),
    _leaf(
        ("Indirect", "Travel & Entertainment", "Airfare"), "6800",
        "Flights and other long-distance travel",
        {"airfare", "flight", "trip", "round", "copenhagen", "stockholm", "berlin",
         "oslo", "london"},
    ),
    _leaf(
        ("Indirect", "Travel & Entertainment", "Lodging"), "6810",
        "Hotels and short-stay apartments",
        {"hotel", "airbnb", "nights", "apartment", "lodging", "corporate"},
    ),
    _leaf(
        ("Indirect", "Travel & Entertainment", "Meals"), "6820",
        "Client meals, catering and entertainment",
        {"dinner", "lunch", "catering", "party", "meals", "entertainment", "client"},
    ),
    _leaf(
        ("Indirect", "Travel & Entertainment", "Ground Transport"), "6830",
        "Rail, bus, taxi, ride-hailing and car hire.",
        {"train", "togbillet", "rail", "bus", "taxi", "metro", "commute",
         "ticket", "dsb", "transport"},
    ),

    TemplateNode(("Indirect", "Financial Services")),
    _leaf(
        ("Indirect", "Financial Services", "Banking & Account Fees"), "7300",
        "Account maintenance, plan and business banking fees.",
        {"bank", "account", "fee", "gebyr", "banking", "overdraft"},
    ),
    _leaf(
        ("Indirect", "Financial Services", "Payment Processing Fees"), "7310",
        "Card acquiring, transaction and payment-method charges.",
        {"card", "acquiring", "transaction", "stripe", "payment", "settlement"},
    ),
    _leaf(
        ("Indirect", "Financial Services", "Levies & Royalties"), "7320",
        "Copyright levies, licensing and royalty charges not tied to a product.",
        {"levy", "royalty", "copydan", "koda", "licensing", "afgift"},
    ),

    TemplateNode(("Indirect", "Insurance")),
    _leaf(
        ("Indirect", "Insurance", "Liability Insurance"), "7200",
        "Third-party and professional liability cover.",
        {"insurance", "liability", "forsikring", "cover", "indemnity"},
    ),
    _leaf(
        ("Indirect", "Insurance", "Employee & Work Accident Insurance"), "7210",
        "Work-accident, health and other cover carried on behalf of employees.",
        {"accident", "health", "employee", "arbejdsskade", "sundhed"},
    ),
    _leaf(
        ("Indirect", "Insurance", "Insurance Levies & Contributions"), "7220",
        "Statutory surcharges and guarantee-fund contributions attached to insurance.",
        {"levy", "guarantee", "fund", "statutory", "contribution"},
    ),

    TemplateNode(("Indirect", "Logistics")),
    _leaf(
        ("Indirect", "Logistics", "Shipping"), "7000",
        "Freight, courier and parcel delivery",
        {"package", "delivery", "freight", "courier", "express", "pallet",
         "shipping", "domestic"},
    ),

    TemplateNode(("Indirect", "People")),
    _leaf(
        ("Indirect", "People", "Contractors"), "7050",
        "Freelancers and contract staff",
        {"contractor", "freelance", "developer", "designer", "qa", "engineer",
         "temp", "staff"},
    ),
    _leaf(
        ("Indirect", "People", "Training"), "7100",
        "Courses, certifications and conference tickets",
        {"course", "training", "certification", "exam", "ticket", "online"},
    ),
)


KEYWORDS_BY_CODE: dict[str, frozenset[str]] = {
    node.code: node.keywords for node in DEFAULT_TEMPLATE if node.code
}
