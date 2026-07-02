# src/spend_predictor/synthdata/catalog.py
"""Deterministic, curated item catalog for synthetic invoice generation.

Public API
----------
line_descriptions(account_code, n, faker) -> list[str]
    Return n realistic, varied line-item descriptions for the account.

vendor_name(account, faker) -> str
    Return an industry-flavored vendor name for the account.

All randomness is delegated to the passed ``faker`` instance so callers can
keep full seed control.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faker import Faker

# ---------------------------------------------------------------------------
# Item catalog — ≥8 templates per account code.
# Templates may contain a ``{spec}`` placeholder that helpers fill.
# ---------------------------------------------------------------------------
ITEM_CATALOG: dict[str, list[str]] = {
    # 6010 Cloud Hosting & Infrastructure
    "6010": [
        "Compute instance {spec} (monthly)",
        "Object storage {spec} — data-at-rest",
        "Managed Kubernetes cluster {spec}",
        "CDN bandwidth — {spec} region",
        "GPU node reservation {spec}",
        "VPC networking & egress — {spec}",
        "Block storage volume {spec}",
        "Load-balancer service — {spec} nodes",
        "Snapshot retention tier {spec}",
        "Bare-metal server lease — {spec}",
    ],
    # 6015 Third-Party APIs & Data
    "6015": [
        "Geocoding API — {spec} requests",
        "Financial data feed {spec} subscription",
        "SMS gateway — {spec} messages",
        "Email delivery API — {spec} sends",
        "Weather & environmental data {spec}",
        "Machine-translation API calls {spec}",
        "Identity verification API — {spec} checks",
        "Market price data stream {spec}",
        "Fraud-detection API — {spec} events",
        "Currency-exchange rate feed {spec}",
    ],
    # 6020 Software Subscriptions
    "6020": [
        "Project management suite — {spec} seats",
        "BI & analytics platform {spec}",
        "CI/CD pipeline license {spec}",
        "Security scanning tool — {spec} repos",
        "Design collaboration tool {spec}",
        "CRM platform — {spec} users",
        "Documentation & wiki SaaS {spec}",
        "Endpoint management software {spec}",
        "Log-aggregation platform — {spec} GB/day",
        "Code-review & repo hosting {spec}",
    ],
    # 6030 Telecommunications
    "6030": [
        "Business broadband — {spec} Mbps line",
        "Mobile data plan {spec} SIM cards",
        "Hosted VoIP — {spec} extensions",
        "SD-WAN managed service {spec}",
        "Dedicated fibre uplink {spec}",
        "International calling bundle {spec}",
        "Video-conferencing bridge service {spec}",
        "IoT SIM pool — {spec} devices",
        "DID number rental — {spec} numbers",
        "Colocation cross-connect port {spec}",
    ],
    # 6500 Office Supplies
    "6500": [
        "A4 printer paper — {spec} reams",
        "Ballpoint pens assorted {spec}",
        "Sticky-note pads {spec} packs",
        "Envelopes C4/C5 — {spec} box",
        "Staples & binding supplies {spec}",
        "Whiteboard markers {spec} sets",
        "Filing folders & labels {spec}",
        "Toner cartridge {spec}",
        "Desk organisers & trays {spec}",
        "Correction tape & highlighters {spec}",
    ],
    # 6510 Office Equipment
    "6510": [
        "27″ monitor {spec}",
        "Standing-desk frame {spec}",
        "Ergonomic office chair {spec}",
        "Mechanical keyboard {spec}",
        "Wireless mouse & pad {spec}",
        "Docking station {spec}",
        "Webcam HD {spec}",
        "Noise-cancelling headset {spec}",
        "Label printer {spec}",
        "UPS battery backup {spec}",
    ],
    # 6600 Professional Services (Consulting)
    "6600": [
        "Strategy consulting — {spec} days",
        "Process-optimisation workshop {spec}",
        "Architecture review {spec}",
        "Change-management advisory {spec}",
        "Data-governance consulting {spec}",
        "Interim CTO engagement {spec}",
        "ERP implementation consulting {spec}",
        "Cloud migration advisory {spec}",
        "Security posture assessment {spec}",
        "Vendor-selection support {spec}",
    ],
    # 6610 Legal Fees
    "6610": [
        "Corporate M&A due-diligence {spec}",
        "Contract drafting & review {spec}",
        "IP trademark registration {spec}",
        "Employment-law advisory {spec}",
        "GDPR compliance counsel {spec}",
        "Dispute mediation services {spec}",
        "Regulatory filing preparation {spec}",
        "Terms-of-service drafting {spec}",
        "Data-processor agreement review {spec}",
        "Commercial lease negotiation {spec}",
    ],
    # 6620 Accounting & Audit
    "6620": [
        "Annual statutory audit {spec}",
        "Quarterly bookkeeping services {spec}",
        "Payroll processing — {spec} employees",
        "VAT return preparation {spec}",
        "Management accounts — {spec}",
        "Tax advisory — {spec}",
        "Transfer-pricing review {spec}",
        "Internal controls assessment {spec}",
        "Year-end accounts preparation {spec}",
        "R&D tax credit claim {spec}",
    ],
    # 6700 Marketing & Advertising
    "6700": [
        "Paid search campaign — {spec}",
        "Social-media advertising {spec}",
        "Content-marketing retainer {spec}",
        "Display banner production {spec}",
        "Influencer campaign management {spec}",
        "Email marketing platform {spec}",
        "Trade-show booth design {spec}",
        "SEO audit & optimisation {spec}",
        "Programmatic ad spend {spec}",
        "Brand-identity refresh {spec}",
    ],
    # 6800 Travel - Airfare
    "6800": [
        "Business-class flight {spec}",
        "Economy round-trip {spec}",
        "Last-minute fare {spec}",
        "Group booking — {spec} pax",
        "Airport transfer & car service {spec}",
        "Airline change fee {spec}",
        "Premium-economy upgrade {spec}",
        "Corporate fare — {spec} route",
        "Excess-baggage fee {spec}",
        "Frequent-flyer redemption top-up {spec}",
    ],
    # 6810 Travel - Lodging
    "6810": [
        "Hotel accommodation — {spec} nights",
        "Serviced apartment {spec}",
        "Conference hotel room block {spec}",
        "Extended-stay lodging {spec}",
        "Airbnb business rental {spec}",
        "Resort fee & parking {spec}",
        "Early check-in / late check-out {spec}",
        "Corporate rate hotel {spec}",
        "Boutique hotel — {spec}",
        "Budget hotel stay {spec}",
    ],
    # 6820 Meals & Entertainment
    "6820": [
        "Client business dinner — {spec} covers",
        "Team lunch — {spec} pax",
        "Working breakfast catering {spec}",
        "Conference catering {spec}",
        "Client entertainment — {spec}",
        "Offsite team dinner {spec}",
        "Executive club membership {spec}",
        "Sponsored hospitality event {spec}",
        "After-work social {spec}",
        "Vendor appreciation dinner {spec}",
    ],
    # 6900 Utilities
    "6900": [
        "Electricity — {spec} kWh",
        "Natural-gas supply {spec}",
        "Water & sewage {spec}",
        "District heating {spec}",
        "Waste collection service {spec}",
        "Facility cleaning services {spec}",
        "Building HVAC maintenance {spec}",
        "Generator fuel — {spec} litres",
        "Solar panel energy credit {spec}",
        "Metering & monitoring services {spec}",
    ],
    # 6910 Rent & Lease
    "6910": [
        "Office-space rent — {spec}",
        "Warehouse lease — {spec} m²",
        "Co-working desk rental {spec}",
        "Equipment lease — {spec}",
        "Car-fleet lease — {spec} vehicles",
        "Short-term storage unit {spec}",
        "Parking-space lease {spec}",
        "Server-room sublease {spec}",
        "Showroom rental {spec}",
        "Meeting-room hire {spec}",
    ],
    # 7000 Shipping & Freight
    "7000": [
        "International air freight {spec}",
        "Sea-freight container {spec}",
        "Express courier delivery {spec}",
        "Last-mile delivery service {spec}",
        "Customs clearance & brokerage {spec}",
        "Refrigerated cargo shipment {spec}",
        "Parcel tracking & insurance {spec}",
        "Pallet storage & handling {spec}",
        "Cross-docking service {spec}",
        "Hazmat freight surcharge {spec}",
    ],
    # 7050 Contractor - Delivery
    "7050": [
        "Freelance developer — {spec} hours",
        "Contract UX designer {spec}",
        "Interim project manager {spec}",
        "On-site DevOps engineer {spec}",
        "Data-engineering contractor {spec}",
        "QA test engineer {spec}",
        "Contract technical writer {spec}",
        "Machine-learning engineer {spec}",
        "Embedded systems contractor {spec}",
        "Security consultant {spec}",
    ],
    # 7100 Training & Development
    "7100": [
        "Online course licence — {spec} seats",
        "In-house workshop — {spec} days",
        "Certification exam fees {spec}",
        "Leadership coaching programme {spec}",
        "Technical skills bootcamp {spec}",
        "Conference attendance {spec}",
        "E-learning platform subscription {spec}",
        "Executive MBA module {spec}",
        "Compliance training {spec}",
        "Hackathon & innovation sprint {spec}",
    ],
}

# ---------------------------------------------------------------------------
# Spec pools — used to fill {spec} placeholders
# ---------------------------------------------------------------------------
_COMPUTE_SIZES = ["4vCPU/16 GB", "8vCPU/32 GB", "2vCPU/8 GB", "16vCPU/64 GB", "c3.large", "m5.xlarge"]
_REGIONS = ["EU-West", "EU-North", "US-East", "US-West", "APAC", "Frankfurt", "Copenhagen", "Virginia"]
_PERIODS = ["(Q1 2026)", "(Q2 2026)", "(Q3 2026)", "(Q4 2025)", "(Jan 2026)", "(Feb 2026)", "(Mar 2026)",
            "(Apr 2026)", "(May 2026)", "(Jun 2026)", "(Jul 2026)", "(Aug 2026)"]
_SKUS = lambda fake: f"[{fake.lexify('??').upper()}-{fake.numerify('####')}]"  # noqa: E731

_CITIES = ["London", "Berlin", "Copenhagen", "Amsterdam", "Paris", "Stockholm", "New York", "Chicago",
           "San Francisco", "Singapore", "Dublin", "Zurich"]
_ROUTES = ["CPH–LHR", "AMS–JFK", "FRA–SFO", "CDG–SIN", "ARN–DXB", "CPH–FRA", "LHR–ORD", "OSL–BOS"]
_VOLUMES = ["50 k", "100 k", "250 k", "500 k", "1 M", "5 M"]
_SEAT_COUNTS = ["5", "10", "20", "50", "100", "unlimited"]
_DAY_COUNTS = ["1", "2", "3", "5", "10"]
_NIGHT_COUNTS = ["2", "3", "4", "5", "7"]
_COVER_COUNTS = ["4", "6", "8", "10", "12"]
_M2 = ["120", "250", "500", "1 000", "2 500"]
_VEHICLE_COUNTS = ["3", "5", "10", "15", "20"]
_EMPLOYEE_COUNTS = ["10", "25", "50", "100", "200"]
_KWH = ["5 000", "12 000", "25 000", "50 000", "100 000"]
_LITRES = ["200", "500", "1 000", "2 000"]
_PAX = ["2", "3", "4", "5", "6"]

# Per-account spec generators: each entry is a callable(fake) -> str
_SPEC_FN: dict[str, list] = {
    "6010": [
        lambda f: f.random_element(_COMPUTE_SIZES),
        lambda f: f"{f.random_element(_VOLUMES)} GB",
        lambda f: f.random_element(_REGIONS),
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
    ],
    "6015": [
        lambda f: f"{f.random_element(_VOLUMES)} calls",
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
        lambda f: f"Tier {f.random_element(['Starter', 'Pro', 'Enterprise'])}",
    ],
    "6020": [
        lambda f: f.random_element(_SEAT_COUNTS) + " seats",
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
        lambda f: f"Plan {f.random_element(['Basic', 'Standard', 'Pro', 'Enterprise'])}",
    ],
    "6030": [
        lambda f: f.random_element(["100", "500", "1 000", "10 000"]) + " Mbps",
        lambda f: str(f.random_int(1, 50)),
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
    ],
    "6500": [
        lambda f: str(f.random_int(1, 20)),
        lambda f: f"{f.random_int(1, 10)} boxes",
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
    ],
    "6510": [
        lambda f: _SKUS(f),
        lambda f: f"Model {f.random_element(['2025', 'Pro', 'Ultra', 'Gen2'])}",
        lambda f: f.random_element(_PERIODS),
    ],
    "6600": [
        lambda f: f"{f.random_element(_DAY_COUNTS)} days",
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
        lambda f: f.random_element(_CITIES),
    ],
    "6610": [
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
        lambda f: f"Matter {f.numerify('####')}",
    ],
    "6620": [
        lambda f: f.random_element(_PERIODS),
        lambda f: f"{f.random_element(_EMPLOYEE_COUNTS)} employees",
        lambda f: _SKUS(f),
        lambda f: f"FY{f.random_element(['2024', '2025', '2026'])}",
    ],
    "6700": [
        lambda f: f.random_element(_REGIONS),
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
        lambda f: f"Budget {f.random_element(['5 k', '10 k', '25 k', '50 k'])} EUR",
    ],
    "6800": [
        lambda f: f.random_element(_ROUTES),
        lambda f: f.random_element(_CITIES),
        lambda f: f.random_element(_PAX) + " pax",
        lambda f: _SKUS(f),
    ],
    "6810": [
        lambda f: f"{f.random_element(_NIGHT_COUNTS)} nights",
        lambda f: f.random_element(_CITIES),
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
    ],
    "6820": [
        lambda f: f"{f.random_element(_COVER_COUNTS)} covers",
        lambda f: f"{f.random_element(_PAX)} pax",
        lambda f: f.random_element(_CITIES),
        lambda f: _SKUS(f),
    ],
    "6900": [
        lambda f: f.random_element(_KWH) + " kWh",
        lambda f: f.random_element(_PERIODS),
        lambda f: f.random_element(_LITRES) + " L",
        lambda f: _SKUS(f),
    ],
    "6910": [
        lambda f: f.random_element(_CITIES),
        lambda f: f"{f.random_element(_M2)} m²",
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
    ],
    "7000": [
        lambda f: f.random_element(_ROUTES),
        lambda f: _SKUS(f),
        lambda f: f.random_element(_REGIONS),
        lambda f: f"Ref {f.numerify('########')}",
    ],
    "7050": [
        lambda f: f"{f.random_element(['40', '80', '120', '160', '200'])} hours",
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
        lambda f: f"PO-{f.numerify('######')}",
    ],
    "7100": [
        lambda f: f.random_element(_SEAT_COUNTS) + " seats",
        lambda f: f"{f.random_element(_DAY_COUNTS)} days",
        lambda f: f.random_element(_PERIODS),
        lambda f: _SKUS(f),
    ],
}

# ---------------------------------------------------------------------------
# Vendor name word pools per industry cluster
# ---------------------------------------------------------------------------
_VENDOR_POOLS: dict[str, tuple[list[str], list[str], list[str]]] = {
    # cluster -> (prefixes, midwords, suffixes)
    "tech": (
        ["Byte", "Cloud", "Nimbus", "Cirrus", "Pixel", "Nexus", "Apex", "Core", "Horizon",
         "Qubit", "Stratus", "Vertex", "Zenith", "Nova", "Synapse", "Prism", "Flux", "Arc"],
        ["Forge", "Wave", "Stack", "Lab", "Works", "Hub", "Grid", "Pulse", "Base", "Vault",
         "Stream", "Spark", "Logic", "Mind", "Scale", "Link"],
        ["Ltd", "GmbH", "Inc", "SAS", "AB", "ApS", "BV", "Corp", "Technologies", "Systems"],
    ),
    "legal": (
        ["Meridian", "Harlow", "Ashford", "Sterling", "Blackwood", "Hadley", "Westbrook",
         "Pemberton", "Clifton", "Vance", "Langley", "Sinclair"],
        ["&", "&"],
        ["LLP", "& Partners", "Law Group", "Solicitors", "Legal Counsel"],
    ),
    "finance": (
        ["Veritas", "Axiom", "Summit", "Alpine", "Meridian", "Clearwater", "Pinnacle",
         "Benchmark", "Capital", "Apex"],
        ["Advisory", "Audit", "Partners", "Consulting", "Finance", "Group", "Associates"],
        ["LLP", "& Co", "CPA", "GmbH", "Ltd"],
    ),
    "marketing": (
        ["Bright", "Bold", "Creative", "Vivid", "Spark", "Radiant", "Amplify", "Catalyst",
         "Signal", "Beacon", "Prism", "Canvas", "Echo"],
        ["Wave", "Media", "Studio", "Agency", "Works", "Creative", "House", "Lab", "Craft"],
        ["Ltd", "Inc", "GmbH", "S.A.", "Agency", "Group", "ApS"],
    ),
    "travel": (
        ["Skyline", "Horizon", "Global", "Premier", "Executive", "Compass", "Meridian",
         "Voyager", "Elite", "Swift"],
        ["Travel", "Air", "Stays", "Lodging", "Hospitality", "Journeys", "Routes"],
        ["Inc", "Ltd", "GmbH", "& Co", "Group"],
    ),
    "logistics": (
        ["HarborLine", "SwiftPath", "IronBridge", "NorthStar", "BlueLine", "TerraRoute",
         "Pacific", "Atlantic", "Crossroads", "Landmark"],
        ["Freight", "Logistics", "Cargo", "Express", "Shipping", "Delivery", "Transport"],
        ["Inc", "Ltd", "GmbH", "& Co", "Group", "S.A."],
    ),
    "facilities": (
        ["Regus", "Nexus", "Cornerstone", "Milestone", "Springbrook", "Highgate", "Clearview",
         "Bridgeway", "Solaris", "Greenfield"],
        ["Office", "Spaces", "Properties", "Facilities", "Estates", "Realty", "Solutions"],
        ["Ltd", "GmbH", "Inc", "Group", "& Co"],
    ),
    "people": (
        ["TalentBridge", "SkillForge", "Elevate", "Propel", "Mentor", "Catalyst", "Ignite",
         "Synergy", "Leverage", "Acumen"],
        ["Consulting", "Solutions", "Group", "Partners", "Services", "Academy", "Learning"],
        ["Ltd", "Inc", "GmbH", "ApS", "& Co"],
    ),
    "generic": (
        ["Atlas", "Summit", "Pinnacle", "Meridian", "Axiom", "Nexus", "Sterling", "Apex",
         "Horizon", "Catalyst"],
        ["Group", "Solutions", "Services", "Partners", "Associates", "Consulting"],
        ["Ltd", "Inc", "GmbH", "& Co", "S.A.", "ApS"],
    ),
}


# Map account codes to vendor clusters
_ACCOUNT_CLUSTER: dict[str, str] = {
    "6010": "tech", "6015": "tech", "6020": "tech", "6030": "tech",
    "6500": "facilities", "6510": "facilities",
    "6600": "people", "6610": "legal", "6620": "finance",
    "6700": "marketing",
    "6800": "travel", "6810": "travel", "6820": "travel",
    "6900": "facilities", "6910": "facilities",
    "7000": "logistics", "7050": "people",
    "7100": "people",
}


def _fill_spec(template: str, account_code: str, fake: "Faker") -> str:
    """Replace {spec} in a template with a contextually appropriate value."""
    if "{spec}" not in template:
        return template
    fns = _SPEC_FN.get(account_code, [])
    if fns:
        # Build list of safe spec generators to avoid double-decoration
        # Skip period specs if template already contains '(', skip SKU specs if it contains '['
        safe_indices = list(range(len(fns)))

        if '(' in template:
            # Filter out functions that return periods (raw _PERIODS selections)
            safe_indices = [
                i for i in safe_indices
                if not _spec_fn_returns_period(fns[i], account_code, i)
            ]

        if '[' in template:
            # Filter out functions that return SKUs
            safe_indices = [
                i for i in safe_indices
                if not _spec_fn_returns_sku(fns[i], account_code, i)
            ]

        # If no safe options, use all (shouldn't happen in practice)
        if not safe_indices:
            safe_indices = list(range(len(fns)))

        safe_fns = [fns[i] for i in safe_indices]
        spec = fake.random_element(safe_fns)(fake)
    else:
        spec = f"[{fake.lexify('??').upper()}-{fake.numerify('####')}]"
    return template.replace("{spec}", spec)


def _spec_fn_returns_period(fn, account_code: str, index: int) -> bool:
    """Check if a spec generator at a given account/index typically returns a period."""
    # Hardcode knowledge of which indices return periods for each account
    period_indices: dict[str, list[int]] = {
        "6010": [3],  # index 3: lambda f: f.random_element(_PERIODS)
        "6015": [1],  # index 1
        "6020": [1],  # index 1
        "6030": [2],  # index 2
        "6500": [2],  # index 2
        "6510": [2],  # index 2
        "6600": [1],  # index 1
        "6610": [0],  # index 0
        "6620": [0],  # index 0
        "6700": [1],  # index 1
        "6810": [2],  # index 2
        "7050": [1],  # index 1
        "7100": [2],  # index 2
        "6900": [1],  # index 1
        "6910": [2],  # index 2
    }
    return index in period_indices.get(account_code, [])


def _spec_fn_returns_sku(fn, account_code: str, index: int) -> bool:
    """Check if a spec generator at a given account/index typically returns an SKU."""
    # Hardcode knowledge of which indices return SKUs for each account
    sku_indices: dict[str, list[int]] = {
        "6010": [4],  # index 4: lambda f: _SKUS(f)
        "6015": [2],  # index 2
        "6020": [2],  # index 2
        "6030": [3],  # index 3
        "6500": [3],  # index 3
        "6510": [0],  # index 0
        "6600": [2],  # index 2
        "6610": [1],  # index 1
        "6620": [2],  # index 2
        "6700": [2],  # index 2
        "6800": [3],  # index 3
        "6810": [3],  # index 3
        "6820": [3],  # index 3
        "6900": [3],  # index 3
        "6910": [3],  # index 3
        "7000": [1],  # index 1
        "7050": [2],  # index 2
        "7100": [3],  # index 3
    }
    return index in sku_indices.get(account_code, [])


def _decorate(desc: str, fake: "Faker") -> str:
    """Optionally append a period or SKU decorator for extra variety."""
    roll = fake.random_int(0, 9)
    if roll < 3:
        # Only append period decorator if description doesn't already contain '('
        if '(' not in desc:
            desc = f"{desc} {fake.random_element(_PERIODS)}"
    elif roll < 5:
        # Only append SKU decorator if description doesn't already contain '['
        if '[' not in desc:
            desc = f"{desc} [{fake.lexify('??').upper()}-{fake.numerify('####')}]"
    return desc


def line_descriptions(account_code: str, n: int, faker: "Faker") -> list[str]:
    """Return n realistic, varied line-item descriptions for the account.

    Uses the ITEM_CATALOG for the account code, fills {spec} placeholders, and
    optionally appends decorators.  All randomness goes through ``faker`` so
    results are fully seed-deterministic.
    """
    templates = ITEM_CATALOG.get(account_code)
    if not templates:
        # Unknown account — synthesise from account code itself
        fallback_word = account_code.replace("_", " ").replace("-", " ")
        templates = [f"{fallback_word} service {{spec}}", f"{fallback_word} item {{spec}}"]

    results: list[str] = []
    used_templates: set[int] = set()
    pool = list(range(len(templates)))

    for _ in range(n):
        # Prefer templates not yet used this invoice; recycle when exhausted
        remaining = [i for i in pool if i not in used_templates]
        if not remaining:
            used_templates.clear()
            remaining = pool
        idx = faker.random_element(remaining)
        used_templates.add(idx)
        raw = _fill_spec(templates[idx], account_code, faker)
        results.append(_decorate(raw, faker))

    return results


def vendor_name(account: dict, faker: "Faker") -> str:
    """Return an industry-flavored vendor name for the account.

    Builds names from curated per-industry word pools so they look realistic
    (e.g. 'ByteForge Cloud GmbH', 'Meridian & Hale LLP') rather than the
    generic Faker ``company()`` default.
    """
    code = account.get("account_code", "")
    cluster = _ACCOUNT_CLUSTER.get(code, "generic")
    prefixes, midwords, suffixes = _VENDOR_POOLS[cluster]

    prefix = faker.random_element(prefixes)
    suffix = faker.random_element(suffixes)

    style = faker.random_int(0, 4)
    if cluster == "legal":
        # e.g. "Meridian & Hale LLP"
        second = faker.random_element(prefixes)
        mid = faker.random_element(midwords)  # "&"
        return f"{prefix} {mid} {second} {suffix}"
    elif style == 0:
        # "PrefixMid Suffix"
        mid = faker.random_element(midwords)
        return f"{prefix}{mid} {suffix}"
    elif style == 1:
        # "Prefix Mid Suffix"
        mid = faker.random_element(midwords)
        return f"{prefix} {mid} {suffix}"
    elif style == 2:
        # "Prefix Suffix" (compact)
        return f"{prefix} {suffix}"
    elif style == 3:
        # "Prefix Mid" (no suffix)
        mid = faker.random_element(midwords)
        return f"{prefix} {mid}"
    else:
        # "PrefixMid"
        mid = faker.random_element(midwords)
        return f"{prefix}{mid}"
