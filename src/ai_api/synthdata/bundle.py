"""Write/read fixture bundles: labels.json per fixture + a manifest.jsonl index."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..models import ExtractedInvoice
from .erp import JournalEntry
from .profiles import BuyerProfile


def category_from_account(account: dict, level1: str) -> dict:
    return {
        "account_code": account["account_code"],
        "account_name": account["account_name"],
        "level1": level1,
        "level2": account["level2"],
        "level3": account["level3"],
    }


def write_labels(
    fixture_dir: Path, *,
    invoice: ExtractedInvoice, category: dict,
    buyer: BuyerProfile, journal: list[JournalEntry],
) -> Path:
    """Write labels.json into fixture_dir (ground-truth for the fixture's PDF)."""
    fixture_dir = Path(fixture_dir)
    fixture_dir.mkdir(parents=True, exist_ok=True)
    labels = {
        "invoice": invoice.model_dump(),
        "category": category,
        "buyer": {
            "name": buyer.name, "website": buyer.website,
            "country_code": buyer.country_code, "vat_number": buyer.vat_number,
            "business_description": buyer.business_description,
        },
        "journal": [asdict(e) for e in journal],
    }
    path = fixture_dir / "labels.json"
    path.write_text(json.dumps(labels, indent=2))
    return path


def append_manifest(manifest_path: Path, entry: dict) -> None:
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def load_fixture(fixture_dir: Path) -> dict:
    """Load a fixture's labels.json (the PDF sits beside it as invoice.pdf)."""
    return json.loads((Path(fixture_dir) / "labels.json").read_text())
