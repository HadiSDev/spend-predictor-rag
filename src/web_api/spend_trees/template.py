"""The platform's default spend-tree template.

This is the single definition of the built-in taxonomy. It used to live as
``_META`` in ``ai_api/sync/categorizer.py``, keyed by *mock ERP account code* —
which made it not a spend tree at all but a mock chart of accounts wearing one,
in the wrong package, invisible to the customer, and uneditable.

Three levels, ``Direct``/``Indirect`` at the first. It is **copied** into an
organization on first use rather than shared: a customer will rename
``Facilities & Office`` on day two and that must not touch another tenant.

``keywords`` are the curated synonyms the deterministic keyword categorizer
matches on. They are carried here, attached to a node by ``code``, rather than
stored as a column: they are a property of *this taxonomy*, not of a spend-tree
node in general, and a customer's own node has none. That asymmetry disappears
when the Qdrant/LLM categorizer lands, which embeds name + description and needs
no curated synonyms at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field


#: Bumped when the node set below changes. Recorded on every copy as
#: ``SpendTree.template_version``; nothing acts on it yet.
TEMPLATE_VERSION = "1"

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


#: Every node, interior and leaf, in the order it should be presented. Interior
#: nodes are listed explicitly rather than implied by their children's paths, so
#: sibling order is stated rather than falling out of dictionary iteration.
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


#: Curated synonyms by node ``code``. The categorizer attaches these to a
#: template-seeded node; a custom node matches on its own name/description.
KEYWORDS_BY_CODE: dict[str, frozenset[str]] = {
    node.code: node.keywords for node in DEFAULT_TEMPLATE if node.code
}
