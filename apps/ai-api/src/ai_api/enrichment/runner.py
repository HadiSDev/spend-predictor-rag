"""CLI for the vendor-enrichment stage."""
from __future__ import annotations

import argparse
import logging

from sqlmodel import Session

from web_api.db.session import engine

from .. import config
from .vendors import describe_vendors

logger = logging.getLogger("ai_api.enrichment")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Describe the suppliers the ledger only names, so a line can "
                    "be categorized from what its supplier actually sells.",
    )
    parser.add_argument(
        "--company-id", default=None,
        help="Work this company's suppliers first (the vendor row is global either way)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Describe at most this many suppliers, to pace a large backlog",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not config.VENDOR_ENRICHMENT_ENABLED:
        print(
            "VENDOR_ENRICHMENT_ENABLED is not set, so nothing was researched.\n"
            "This stage reaches the public web and writes to the global supplier\n"
            "catalog, so it is opt-in. Set it in .env to enable."
        )
        return 0

    with Session(engine) as session:
        result = describe_vendors(
            session, company_id=args.company_id, limit=args.limit
        )

    if not result.considered:
        print("Every supplier in scope already has a description.")
        return 0

    print("\n=== vendor enrichment ===")
    for key, value in result.as_dict.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
