"""Integration test for the sync runner against an in-memory DB + fake connector.

Exercises the entry-first flow: fetch entries → group by voucher → fetch invoice
scans per voucher → persist (Invoice + lines + File, entries linked via voucher) →
categorize. Runs without a live Postgres or the mock ERP HTTP server.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, func, select

from web_api.connectors import register_connector
from web_api.connectors.base import (
    ErpAccountData,
    ErpConnector,
    ErpEntryData,
    ErpInvoiceData,
    ErpInvoiceLineData,
    ErpVendorData,
)
from web_api.db.models import (
    AuditLog,
    ErpAccount,
    ErpEntry,
    File,
    Invoice,
    InvoiceLine,
    SyncState,
    Vendor,
)
from ai_api.persistence import LineGroundTruth
from ai_api.sync import runner


# Two invoice vouchers (V1 matchable, V2 unmatchable) plus a payment voucher with
# no invoice scan. Each invoice voucher posts three entries: net debit, VAT debit,
# AP credit. The payment voucher posts two entries and must stay unlinked.
_SCANS = {
    "V1": ErpInvoiceData(
        erp_id="INV1", vendor_erp_id="V1", vendor_name="NordicCloud Solutions ApS",
        invoice_number="INV1", invoice_date=date(2025, 7, 15), currency="DKK",
        total=1250.0, tax=250.0, voucher_id="V1",
        file_name="invoice_INV1.pdf", file_ref="scans/V1/invoice_INV1.pdf",
        lines=[ErpInvoiceLineData(line_erp_id="1", description="Cloud server - monthly hosting",
                                  amount=1000.0, native_account_code="6010")],
    ),
    "V2": ErpInvoiceData(
        erp_id="INV2", vendor_erp_id="V1", vendor_name="NordicCloud Solutions ApS",
        invoice_number="INV2", invoice_date=date(2025, 8, 3), currency="DKK",
        total=500.0, tax=100.0, voucher_id="V2",
        file_name="invoice_INV2.pdf", file_ref="scans/V2/invoice_INV2.pdf",
        lines=[ErpInvoiceLineData(line_erp_id="1", description="zzz qqq xyzzy",
                                  amount=400.0, native_account_code=None)],
    ),
}


class _FakeConnector(ErpConnector):
    """Deterministic in-memory ERP, entry-first."""

    def authorize(self) -> str:
        return "fake-token"

    def test_connection(self) -> bool:
        return True

    def fetch_accounts(self) -> list[ErpAccountData]:
        return [
            ErpAccountData(erp_account_code="6010", erp_account_name="Cloud Hosting & Infrastructure",
                           erp_account_type="expense", with_vat=True),
            ErpAccountData(erp_account_code="6020", erp_account_name="Software Subscriptions",
                           erp_account_type="expense"),
            ErpAccountData(erp_account_code="2100", erp_account_name="Accounts Payable",
                           erp_account_type="liability"),
            ErpAccountData(erp_account_code="2200", erp_account_name="VAT Payable",
                           erp_account_type="liability"),
            ErpAccountData(erp_account_code="1000", erp_account_name="Cash",
                           erp_account_type="asset"),
        ]

    def fetch_vendors(self, since=None) -> list[ErpVendorData]:
        return [ErpVendorData(erp_id="V1", name="NordicCloud Solutions ApS", country_code="DK")]

    def fetch_invoices(self, since=None) -> list[ErpInvoiceData]:
        return list(_SCANS.values())

    def fetch_entries(self, since=None, account_codes=None) -> list[ErpEntryData]:
        def pi(eid, voucher, code, d, debit=0.0, credit=0.0, dt=None):
            return ErpEntryData(erp_entry_id=eid, voucher_id=voucher,
                                entry_type="purchase_invoice", erp_account_code=code,
                                entry_date=dt, debit_amount=debit, credit_amount=credit,
                                currency="DKK")
        if account_codes is not None and len(account_codes) == 0:
            return []
        all_entries = [
            pi("E1", "V1", "6010", None, debit=1000.0, dt=date(2025, 7, 15)),
            pi("E2", "V1", "2200", None, debit=250.0, dt=date(2025, 7, 15)),
            pi("E3", "V1", "2100", None, credit=1250.0, dt=date(2025, 7, 15)),
            pi("E4", "V2", "6020", None, debit=400.0, dt=date(2025, 8, 3)),
            pi("E5", "V2", "2200", None, debit=100.0, dt=date(2025, 8, 3)),
            pi("E6", "V2", "2100", None, credit=500.0, dt=date(2025, 8, 3)),
            # Payment voucher — no invoice scan, must stay unlinked.
            ErpEntryData(erp_entry_id="E7", voucher_id="P1", entry_type="payment",
                         erp_account_code="2100", debit_amount=1250.0, currency="DKK"),
            ErpEntryData(erp_entry_id="E8", voucher_id="P1", entry_type="payment",
                         erp_account_code="1000", credit_amount=1250.0, currency="DKK"),
        ]
        if account_codes is None:
            return all_entries
        return [e for e in all_entries if e.erp_account_code in account_codes]

    def fetch_invoice_scan(self, voucher_id: str) -> ErpInvoiceData | None:
        return _SCANS.get(voucher_id)


@pytest.fixture
def sqlite_engine(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(runner, "engine", engine)
    register_connector("fake", _FakeConnector)
    return engine


def test_run_sync_end_to_end(sqlite_engine):
    summary = runner.run_sync("fake", reset=False)

    assert summary["vendors"] == 1
    assert summary["invoices"] == 2
    assert summary["lines"] == 2
    # One line matches (ai_categorized); one fails (ai_failed). Each invoice has a
    # single line, so both invoices roll up to the in-progress "categorized" state.
    assert summary["line_status"] == {"ai_categorized": 1, "ai_failed": 1}
    assert summary["invoice_status"] == {"categorized": 2}
    # Only the categorized line's amount counts toward spend.
    assert summary["categorized_spend"] == 1000.0
    assert summary["spend_by_level_2"] == {"Technology": 1000.0}
    # 8 entries persisted; the 6 purchase-invoice entries link, the 2 payments don't.
    assert summary["entries"] == 8
    assert summary["entries_linked"] == 6

    # The categorization result now lives directly on the line…
    for col in ("level_1", "level_2", "level_3", "account_code", "account_name",
                "confidence", "rationale"):
        assert col in InvoiceLine.__table__.columns
    # …but synthetic ground truth and the ERP line id never touch the domain line.
    for col in ("gt_level_1", "gt_account_code", "line_erp_id"):
        assert col not in InvoiceLine.__table__.columns

    with Session(sqlite_engine) as s:
        ok = s.exec(select(InvoiceLine).where(InvoiceLine.status == "ai_categorized")).one()
        assert ok.account_code == "6010"
        assert ok.level_2 == "Technology"
        assert ok.confidence is not None
        assert ok.rationale
        # No spend tree seeded yet, so the accepted assignment stays null.
        assert ok.spend_category_id is None
        # Ground truth is recorded in the ai_api-owned store, not on the line.
        ok_gt = s.exec(select(LineGroundTruth)
                       .where(LineGroundTruth.invoice_line_id == ok.id)).one()
        assert ok_gt.gt_account_code == "6010"

        bad = s.exec(select(InvoiceLine).where(InvoiceLine.status == "ai_failed")).one()
        assert bad.account_code is None                  # no prediction on the line
        assert bad.error_message

        # One ground-truth row per processed line.
        assert s.exec(select(func.count()).select_from(LineGroundTruth)).one() == 2
        assert s.exec(select(func.count()).select_from(InvoiceLine)
                      .where(InvoiceLine.status == "uncategorized")).one() == 0

        # Each AI categorization is attributed to the system in the audit log.
        sys_rows = s.exec(select(AuditLog).where(
            AuditLog.entity_type == "invoice_line", AuditLog.actor == "system")).all()
        assert len(sys_rows) == 2
        assert all(r.action == "ai_categorize" for r in sys_rows)

        state = s.exec(select(SyncState)).one()
        assert state.status == "idle"
        assert state.last_invoice_date == date(2025, 8, 3)


def test_verified_line_not_overwritten_by_resync(sqlite_engine):
    runner.run_sync("fake", reset=False)

    # A human verifies the categorized line, correcting the account.
    with Session(sqlite_engine) as s:
        ln = s.exec(select(InvoiceLine).where(InvoiceLine.status == "ai_categorized")).one()
        ln.status = "verified"
        ln.account_code = "6610"
        s.add(ln)
        s.commit()
        line_id = ln.id

    # A re-sync must not re-categorize (overwrite) the verified line.
    runner.run_sync("fake", reset=False)
    with Session(sqlite_engine) as s:
        ln = s.get(InvoiceLine, line_id)
        assert ln.status == "verified"
        assert ln.account_code == "6610"


def test_invoice_has_file_and_no_voucher_column(sqlite_engine):
    runner.run_sync("fake", reset=False)

    # The invoice scan references the internal File domain, and is a purely
    # internal document: no voucher, no ERP id, no integration link of its own.
    assert "voucher_id" not in Invoice.__table__.columns
    assert "erp_id" not in Invoice.__table__.columns
    assert "erp_integration_id" not in Invoice.__table__.columns
    assert "erp_integration_id" not in InvoiceLine.__table__.columns
    assert "file_id" in Invoice.__table__.columns
    # Invoice links to the (global) vendor; lines do not. Vendors are not
    # company-scoped and carry no ERP identity.
    assert "vendor_id" in Invoice.__table__.columns
    assert "vendor_id" not in InvoiceLine.__table__.columns
    for col in ("company_id", "erp_id", "raw_json"):
        assert col not in Vendor.__table__.columns

    with Session(sqlite_engine) as s:
        inv1 = s.exec(select(Invoice).where(Invoice.invoice_number == "INV1")).one()
        assert inv1.file_id is not None
        file = s.get(File, inv1.file_id)
        assert file is not None
        assert file.filename == "invoice_INV1.pdf"
        assert file.file_type == "invoice_pdf"


def test_entries_link_to_invoice_via_voucher(sqlite_engine):
    runner.run_sync("fake", reset=False)

    with Session(sqlite_engine) as s:
        inv1 = s.exec(select(Invoice).where(Invoice.invoice_number == "INV1")).one()
        # All three V1 entries carry the voucher and point at the one invoice.
        v1_entries = s.exec(select(ErpEntry).where(ErpEntry.voucher_id == "V1")).all()
        assert len(v1_entries) == 3
        assert all(e.source_invoice_id == inv1.id for e in v1_entries)
        assert all(e.voucher_id == "V1" for e in v1_entries)

        # Payment voucher entries are persisted but unlinked.
        pay = s.exec(select(ErpEntry).where(ErpEntry.voucher_id == "P1")).all()
        assert len(pay) == 2
        assert all(e.source_invoice_id is None for e in pay)


def test_entries_are_not_categorized(sqlite_engine):
    runner.run_sync("fake", reset=False)

    with Session(sqlite_engine) as s:
        entries = s.exec(select(ErpEntry)).all()
        assert len(entries) == 8
        # Entries are raw financial context — categorization never touches them,
        # and the table carries no categorization columns at all.
        for e in entries:
            assert e.status == "pending"
    for col in ("level_1", "level_2", "level_3", "account_code", "account_name",
                "confidence", "rationale", "gt_account_code"):
        assert col not in ErpEntry.__table__.columns


def _acct(session, code: str) -> ErpAccount:
    return session.exec(select(ErpAccount).where(ErpAccount.erp_account_code == code)).one()


def test_with_vat_persisted_from_erp(sqlite_engine):
    runner.run_sync("fake", reset=False)
    with Session(sqlite_engine) as s:
        assert _acct(s, "6010").with_vat is True   # expense account, with VAT
        assert _acct(s, "2100").with_vat is False   # balance-sheet, without VAT
        # New accounts default to enabled.
        assert _acct(s, "6010").sync_enabled is True


def test_disabled_account_yields_no_entries(sqlite_engine):
    # First sync populates accounts + entries (E1 posts to account 6010).
    runner.run_sync("fake", reset=False)
    with Session(sqlite_engine) as s:
        acct6010 = _acct(s, "6010")
        assert s.exec(select(func.count()).select_from(ErpEntry)
                      .where(ErpEntry.erp_account_id == acct6010.id)).one() == 1
        # Deselect 6010 and clear its already-synced entry, so a re-sync proves
        # the fetch-time gate does not pull it again.
        for e in s.exec(select(ErpEntry).where(ErpEntry.erp_account_id == acct6010.id)).all():
            s.delete(e)
        acct6010.sync_enabled = False
        s.add(acct6010)
        s.commit()

    runner.run_sync("fake", reset=False)
    with Session(sqlite_engine) as s:
        acct6010 = _acct(s, "6010")
        assert acct6010.sync_enabled is False   # selection survived the re-sync
        assert acct6010.with_vat is True         # metadata still refreshed
        assert s.exec(select(func.count()).select_from(ErpEntry)
                      .where(ErpEntry.erp_account_id == acct6010.id)).one() == 0
        # Entries for still-enabled accounts are (re)fetched as normal.
        assert s.exec(select(func.count()).select_from(ErpEntry)
                      .where(ErpEntry.erp_account_id == _acct(s, "2100").id)).one() > 0


def test_run_sync_is_idempotent(sqlite_engine):
    first = runner.run_sync("fake", reset=False)
    second = runner.run_sync("fake", reset=False)
    assert first["vendors"] == second["vendors"]
    assert first["lines"] == second["lines"]
    assert first["entries"] == second["entries"]

    with Session(sqlite_engine) as s:
        assert s.exec(select(func.count()).select_from(Vendor)).one() == 1
        assert s.exec(select(func.count()).select_from(InvoiceLine)).one() == 2
        assert s.exec(select(func.count()).select_from(ErpEntry)).one() == 8
        assert s.exec(select(func.count()).select_from(File)).one() == 2
