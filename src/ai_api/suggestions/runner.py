"""CLI for the tree-gap suggester.

    python -m ai_api.suggestions.runner [--company-id ID]

Discovers its work from the database like every other stage here: every active
company with an assigned tree, or the one named. Writes proposals and nothing
else — no `SpendCategory` is created, renamed, moved or deleted by this process.
"""
from __future__ import annotations

import argparse
import logging

from sqlmodel import Session, select

from web_api.db.models import Company
from web_api.db.session import engine

from .gaps import suggest_gaps

logger = logging.getLogger("ai_api.suggestions")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Propose the spend categories a company's tree is missing, "
                    "evidenced by the lines that fit nowhere well.",
    )
    parser.add_argument("--company-id", default=None, help="Only this company")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with Session(engine) as session:
        statement = select(Company).where(Company.spend_tree_id.is_not(None))
        if args.company_id is not None:
            statement = statement.where(Company.id == args.company_id)
        else:
            # An unnamed run covers active companies only, the same rule the
            # unfiltered API listings follow.
            statement = statement.where(Company.is_active == True)  # noqa: E712
        companies = list(session.exec(statement.order_by(Company.name)).all())

        if not companies:
            print("No company with an assigned spend tree.")
            return 0

        total = 0
        for company in companies:
            run = suggest_gaps(session, company.id)
            total += run.proposed
            print(f"\n=== {company.name} ===")
            for key, value in run.as_dict.items():
                print(f"{key}: {value}")
            for note in run.notes:
                print(f"note: {note}")

    print(f"\n{total} suggestion(s) pending review.")
    # Proposing nothing is the good outcome, not a failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
