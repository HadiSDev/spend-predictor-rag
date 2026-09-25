"""Describe a supplier once, for everyone."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from sqlmodel import Session, select

from web_api.db.models import Invoice, Vendor

from .. import config
from ..web_context import get_supplier_context

logger = logging.getLogger("ai_api.enrichment")

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
    """Vendors with no description yet, ordered by name."""
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
    """Research and store a description for every vendor that has none."""
    if enabled is None:
        enabled = config.VENDOR_ENRICHMENT_ENABLED
    if not enabled:
        logger.info("vendor enrichment is disabled; nothing was requested")
        return EnrichmentResult(0, 0, 0, 0)

    if describe is None:
        describe = get_supplier_context

    pending = vendors_needing_description(session, company_id=company_id, limit=limit)
    described = not_found = skipped = 0

    for vendor in pending:
        if (vendor.description or "").strip():
            skipped += 1
            continue
        try:
            note = (describe(vendor.name, vendor.country_code) or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not describe %s: %s", vendor.name, exc)
            not_found += 1
            continue

        if not note:
            not_found += 1
            continue

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
