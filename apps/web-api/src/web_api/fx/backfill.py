"""Ops entry point for recomputing stored base amounts.

    python -m web_api.fx.backfill                      # every active company
    python -m web_api.fx.backfill --company-id <id>    # just one
    python -m web_api.fx.backfill --include-inactive

Use after enabling FX over existing data, after a rate correction, or after a
customer switches base currency and the request-time recompute is too large to
sit in an HTTP call. Needs `FX_ENABLED=true` to fetch anything it does not
already have cached — without it the run is a no-op that reports every row as
unconverted.
"""
from __future__ import annotations

import argparse
import logging
import sys

from sqlmodel import Session, select

from .. import config
from ..db.models import Company
from ..db.session import engine
from .recompute import recompute_company
from .service import CONVERTED, UNCHANGED, UNCONVERTED, FxService

logger = logging.getLogger("web_api.fx.backfill")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recompute stored base-currency amounts.")
    parser.add_argument("--company-id", help="recompute one company (default: all)")
    parser.add_argument("--include-inactive", action="store_true",
                        help="also recompute deactivated companies")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not config.FX_ENABLED:
        logger.warning(
            "FX_ENABLED is off — only already-cached rates are available, so "
            "rows without one will stay unconverted."
        )

    with Session(engine) as session:
        statement = select(Company)
        if args.company_id:
            statement = statement.where(Company.id == args.company_id)
        elif not args.include_inactive:
            statement = statement.where(Company.is_active == True)  # noqa: E712
        companies = session.exec(statement).all()

        if not companies:
            logger.error("No matching companies.")
            return 1

        # One service across the whole run: a rate date shared by two companies
        # is fetched once.
        fx = FxService(session)
        failed = False
        for company in companies:
            try:
                counts = recompute_company(session, company.id, fx=fx)
                session.commit()
            except Exception as exc:
                # One company's failure is not the run's: the rest still get done.
                session.rollback()
                logger.error("[%s] FAILED: %s", company.name, exc)
                failed = True
                continue
            logger.info(
                "[%s] → %s: %d converted, %d unconverted, %d unchanged",
                company.name, company.base_currency,
                counts[CONVERTED], counts[UNCONVERTED], counts[UNCHANGED],
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
