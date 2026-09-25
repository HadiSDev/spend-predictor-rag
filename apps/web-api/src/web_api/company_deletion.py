"""Destroying a company and everything it owns."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlmodel import Session, delete, select

from .db.models import (
    AuditLog,
    Company,
    ErpAccount,
    ErpCredential,
    ErpEntry,
    ErpIntegration,
    File,
    Invoice,
    InvoiceLine,
    Recommendation,
    SpendCategorySuggestion,
    SyncState,
)

_AUDITED_ENTITY_TYPES = ("invoice", "invoice_line")


@dataclass(frozen=True)
class CompanyRecords:
    """What a company holds, for the confirmation a deletion is refused with."""

    invoices: int
    lines: int
    entries: int
    integrations: int
    earliest: date | None
    latest: date | None

    @property
    def is_empty(self) -> bool:
        """Nothing worth previewing."""
        return not (self.invoices or self.lines or self.entries or self.integrations)


def company_records(session: Session, company_id: str) -> CompanyRecords:
    """Count what deleting ``company_id`` would destroy."""
    invoices, earliest, latest = session.exec(
        select(
            func.count(Invoice.id),
            func.min(Invoice.invoice_date),
            func.max(Invoice.invoice_date),
        ).where(Invoice.company_id == company_id)
    ).one()
    lines = session.exec(
        select(func.count(InvoiceLine.id)).where(InvoiceLine.company_id == company_id)
    ).one()
    entries, entry_earliest, entry_latest = session.exec(
        select(
            func.count(ErpEntry.id),
            func.min(ErpEntry.accounting_date),
            func.max(ErpEntry.accounting_date),
        ).where(ErpEntry.company_id == company_id)
    ).one()
    integrations = session.exec(
        select(func.count(ErpIntegration.id)).where(
            ErpIntegration.company_id == company_id
        )
    ).one()

    dates = [d for d in (earliest, latest, entry_earliest, entry_latest) if d is not None]
    return CompanyRecords(
        invoices=invoices or 0,
        lines=lines or 0,
        entries=entries or 0,
        integrations=integrations or 0,
        earliest=min(dates) if dates else None,
        latest=max(dates) if dates else None,
    )


def delete_company(session: Session, company: Company) -> CompanyRecords:
    """Delete ``company`` and every record scoped to it."""
    counts = company_records(session, company.id)

    invoice_ids = list(
        session.exec(select(Invoice.id).where(Invoice.company_id == company.id)).all()
    )
    line_ids = list(
        session.exec(
            select(InvoiceLine.id).where(InvoiceLine.company_id == company.id)
        ).all()
    )
    audited_ids = invoice_ids + line_ids
    if audited_ids:
        session.exec(
            delete(AuditLog).where(
                AuditLog.entity_type.in_(_AUDITED_ENTITY_TYPES),  # type: ignore[attr-defined]
                AuditLog.entity_id.in_(audited_ids),  # type: ignore[attr-defined]
            )
        )

    session.exec(delete(ErpEntry).where(ErpEntry.company_id == company.id))
    session.exec(delete(InvoiceLine).where(InvoiceLine.company_id == company.id))
    session.exec(delete(Invoice).where(Invoice.company_id == company.id))
    session.exec(delete(File).where(File.company_id == company.id))
    session.exec(delete(Recommendation).where(Recommendation.company_id == company.id))
    session.exec(
        delete(SpendCategorySuggestion).where(
            SpendCategorySuggestion.company_id == company.id
        )
    )

    integration_ids = select(ErpIntegration.id).where(
        ErpIntegration.company_id == company.id
    )
    session.exec(
        delete(SyncState).where(SyncState.erp_integration_id.in_(integration_ids))  # type: ignore[attr-defined]
    )
    session.exec(
        delete(ErpCredential).where(
            ErpCredential.erp_integration_id.in_(integration_ids)  # type: ignore[attr-defined]
        )
    )
    session.exec(
        delete(ErpAccount).where(ErpAccount.erp_integration_id.in_(integration_ids))  # type: ignore[attr-defined]
    )
    session.exec(delete(ErpIntegration).where(ErpIntegration.company_id == company.id))

    session.delete(company)
    return counts
