"""Destroying a company and everything it owns.

Companies are soft-deactivated by default, and that stays the right answer
whenever the ledger still means something — deactivation is reversible, keeps
every record, and leaves the company reachable by id. This module is for the
other case: a company that should not exist. Created with a typo, a trial that
never synced, a test tenant wired to an ERP that no longer answers, or one a
customer has asked to have removed rather than merely hidden.

**The deletion is written out, not delegated to the database.** Every foreign key
into ``companies`` is ``NO ACTION`` — there is not one ``ON DELETE CASCADE``
anywhere in the schema — so a bare ``DELETE FROM companies`` fails on the first
child. That is deliberate and stays that way: cascades would make *every* future
company delete silent, including one typed into a shell by mistake or one a later
feature performs without knowing what hangs off a company. Written out, the blast
radius is one function a reviewer can read, and a table added later that nobody
adds here fails loudly on a foreign-key violation rather than orphaning quietly.

The one exception in the whole schema is ``line_ground_truth.invoice_line_id``,
which really is ``ON DELETE CASCADE``. That is load-bearing: the table is owned
by ``ai_api`` and ``web_api`` may not import it, so the database is the only
thing that can clean it up when a line goes.
"""
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

#: The audit rows a company's deletion takes with it. Only these two entity
#: types are ever written (see `audit.py`), and both are company-scoped.
_AUDITED_ENTITY_TYPES = ("invoice", "invoice_line")


@dataclass(frozen=True)
class CompanyRecords:
    """What a company holds, for the confirmation a deletion is refused with.

    Counts rather than a sentence, because the operator's question is "how much
    am I about to destroy" and "some data" does not answer it. The date span is
    what makes a company recognisable when its name does not — a tenant with
    four years of postings reads very differently from one with a week's.
    """

    invoices: int
    lines: int
    entries: int
    integrations: int
    earliest: date | None
    latest: date | None

    @property
    def is_empty(self) -> bool:
        """Nothing worth previewing.

        An empty company deletes without a confirmation gate: there is nothing
        to warn about, and a dialog over nothing is ceremony that teaches the
        operator to click through the one that matters.
        """
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

    # The span covers both dated axes. An invoice carries the document's date and
    # a posting the ledger's, and a company may well hold one without the other —
    # a scan queued before its voucher synced, or a journal entry with no invoice
    # behind it at all.
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
    """Delete ``company`` and every record scoped to it. Returns what went.

    Staged, not committed: the caller owns the transaction, the same discipline
    `integrations.provision_integration` follows. That is what makes the whole
    purge atomic — a failure part-way leaves the company exactly as it was.

    Order is children before parents, because nothing cascades:

    * postings before invoices — `ErpEntry.source_invoice_id` points at them
    * lines before invoices — and `line_ground_truth` follows each line by its
      own cascade, which is the only reason `ai_api`'s table needs no mention
    * invoices before files — `Invoice.file_id` points at them
    * accounts, credentials and sync state before their integration
    """
    counts = company_records(session, company.id)

    # Read the ids *before* anything is deleted: `AuditLog` carries no company
    # id and no foreign key — its only tenancy anchor is the entity it names —
    # so once the invoices and lines are gone there is nothing left to derive
    # them from, and the rows would be unattributable forever.
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
    # Scoped to the company, though the *tree* it proposes into is the
    # organization's and survives. A suggestion argues from a particular
    # company's lines, and those lines are gone.
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

    # `Vendor` is deliberately untouched. The supplier catalog is **global** and
    # shared across tenants: a supplier is not this company's to remove, and
    # another organization may already reference the same row. One left pointed
    # at by nothing is not an orphan — it is a supplier nobody has bought from
    # yet, which is the state every vendor starts in.
    #
    # `SpendTree` and `SpendCategory` likewise. A tree belongs to the
    # *organization* and several companies may share one — a bookkeeping firm
    # running a single taxonomy across its clients is the case the design exists
    # for — so taking it with one of them would silently recategorize the rest.

    session.delete(company)
    return counts
