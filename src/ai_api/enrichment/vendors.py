"""Describe a supplier once, for everyone.

`Vendor` is a **global** catalog: the same supplier seen by different companies
collapses onto one row (`ai_api.sync.runner._vendor_key`). That is what makes
this affordable — DSB is researched once and every tenant that has ever bought a
train ticket reads the answer — and it is also the constraint. What this writes
is prose every tenant sees, so it describes the supplier's trade and nothing
about anybody's relationship with them.

**Why it is a stage and not a step in categorization.** Putting a web search on
the per-line path would make a slow network look like a slow categorizer, and
would research the same supplier once per line. It runs like the document stage
does: separately, over what the database says needs doing.

**Why it is off by default.** It reaches the public web, so the suite and any
offline run must make no request without somebody having asked. `FX_ENABLED` sets
the same rule for the same reason.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from sqlmodel import Session, select

from web_api.db.models import Invoice, Vendor

from .. import config

logger = logging.getLogger("ai_api.enrichment")

#: A description this stage wrote. The other value, ``human``, is set by the
#: migration for anything that predates the column and by any future correction
#: path; either way it is never overwritten here.
WEB = "web"
HUMAN = "human"


@dataclass(frozen=True)
class EnrichmentResult:
    considered: int
    described: int
    not_found: int
    skipped: int

    @property
    def as_dict(self) -> dict[str, int]:
        return {
            "considered": self.considered,
            "described": self.described,
            "not_found": self.not_found,
            "skipped": self.skipped,
        }


def vendors_needing_description(
    session: Session, *, company_id: str | None = None, limit: int | None = None
) -> list[Vendor]:
    """Vendors with nothing said about them, most-referenced first is not needed —
    order is by name so a partial run is repeatable.

    ``company_id`` narrows to suppliers *that company* has invoices from. The
    vendor row itself is global and is written globally either way; the filter
    only decides whose backlog is worked first, which is the useful thing when
    one customer is waiting on their own ledger.
    """
    statement = select(Vendor).where(
        (Vendor.description.is_(None)) | (Vendor.description == "")  # type: ignore[union-attr]
    )
    if company_id is not None:
        referenced = select(Invoice.vendor_id).where(
            Invoice.company_id == company_id,
            Invoice.vendor_id.is_not(None),  # type: ignore[union-attr]
        )
        statement = statement.where(Vendor.id.in_(referenced))  # type: ignore[union-attr]
    statement = statement.order_by(Vendor.name)
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.exec(statement).all())


def describe_vendors(
    session: Session,
    *,
    company_id: str | None = None,
    limit: int | None = None,
    enabled: bool | None = None,
    describe: Callable[[str, str | None], str] | None = None,
) -> EnrichmentResult:
    """Research and store a description for every vendor that has none.

    Commits once at the end: a partial run leaves nothing half-written, and each
    row is independent so there is nothing to unwind on failure.

    ``describe`` is the seam — any callable taking ``(name, country_code)`` and
    returning a description or ``""``. Tests pass a stub, so the suite needs no
    network and no model.
    """
    if enabled is None:
        enabled = config.VENDOR_ENRICHMENT_ENABLED
    if not enabled:
        logger.info("vendor enrichment is disabled; nothing was requested")
        return EnrichmentResult(0, 0, 0, 0)

    if describe is None:
        from ..web_context import get_supplier_context

        def describe(name: str, country_code: str | None) -> str:  # type: ignore[misc]
            return get_supplier_context(name, country_code)

    pending = vendors_needing_description(session, company_id=company_id, limit=limit)
    described = not_found = skipped = 0

    for vendor in pending:
        # Re-checked per row rather than trusted from the query. The select runs
        # once and the loop then takes minutes — a lookup apiece — so on a shared
        # catalog a human edit or a second run landing inside that window is
        # ordinary, not exotic.
        if (vendor.description or "").strip():
            skipped += 1
            continue
        try:
            note = (describe(vendor.name, vendor.country_code) or "").strip()
        except Exception as exc:  # noqa: BLE001 - a lookup is never worth a failure
            # Nothing is written and nothing is raised. A supplier we could not
            # describe is a slightly worse prompt, not a broken ledger, and the
            # next run tries again because the column is still null.
            logger.warning("could not describe %s: %s", vendor.name, exc)
            not_found += 1
            continue

        if not note:
            not_found += 1
            continue

        # Checked again on the far side of the lookup, which is where the window
        # actually is: `describe` is a web search and a model call, seconds wide,
        # and the first check happened before it. Cheap, and the alternative is
        # overwriting a correction with a guess.
        session.refresh(vendor)
        if (vendor.description or "").strip():
            skipped += 1
            continue

        vendor.description = note
        vendor.description_source = WEB
        session.add(vendor)
        described += 1
        logger.info("described %s: %s", vendor.name, note[:80])

    session.commit()
    return EnrichmentResult(
        considered=len(pending), described=described,
        not_found=not_found, skipped=skipped,
    )
