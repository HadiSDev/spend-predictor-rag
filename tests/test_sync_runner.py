"""Integration test for the sync runner against an in-memory DB + fake connector.

Exercises the entry-first flow: fetch entries → group by voucher → fetch invoice
scans per voucher → persist (Invoice + lines + File, entries linked via voucher) →
categorize. Runs without a live Postgres or the mock ERP HTTP server.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, func, select

from web_api.connectors import register_connector
from web_api.connectors.base import (
    DocumentPayload,
    ErpAccountData,
    ErpConnector,
    ErpEntryData,
    ErpInvoiceData,
    ErpInvoiceLineData,
    ErpVendorData,
)
from web_api.db.models import (
    AuditLog,
    Company,
    ErpAccount,
    ErpEntry,
    ErpIntegration,
    File,
    Invoice,
    InvoiceLine,
    Organization,
    SpendCategory,
    SyncState,
    Vendor,
)
from web_api.fx import FxService
from web_api.rollup import recompute_invoice_status
from web_api.spend_trees.service import ensure_default_tree
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
        def pi(eid, voucher, code, line_no, debit=0.0, credit=0.0, dt=None):
            # `line_no` is the invoice line this posting came from, or None for
            # the VAT and payable postings, which belong to no single line.
            return ErpEntryData(erp_entry_id=eid, voucher_id=voucher,
                                entry_type="purchase_invoice", erp_account_code=code,
                                source_line_erp_id=line_no,
                                accounting_date=dt, debit_amount=debit, credit_amount=credit,
                                currency="DKK")
        if account_codes is not None and len(account_codes) == 0:
            return []
        all_entries = [
            pi("E1", "V1", "6010", "1", debit=1000.0, dt=date(2025, 7, 15)),
            pi("E2", "V1", "2200", None, debit=250.0, dt=date(2025, 7, 15)),
            pi("E3", "V1", "2100", None, credit=1250.0, dt=date(2025, 7, 15)),
            pi("E4", "V2", "6020", "1", debit=400.0, dt=date(2025, 8, 3)),
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

    def fetch_invoice_document(self, voucher_id: str) -> DocumentPayload | None:
        return None


@pytest.fixture
def sqlite_engine(monkeypatch):
    """An engine plus one connected integration for the runner to discover.

    The tenant is built here rather than by the runner: `run_sync` reads its
    work from the database and never creates an organization or a company.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(runner, "engine", engine)
    register_connector("fake", _FakeConnector)

    with Session(engine) as s:
        org = Organization(name="Test Org", clerk_org_id="clerk_test")
        s.add(org)
        s.commit()
        # The company must be assigned a spend tree, exactly as `POST /companies`
        # assigns one: the runner categorizes against the customer's own
        # taxonomy and has no built-in fallback to invent one from.
        tree = ensure_default_tree(s, org.id)
        s.commit()
        company = Company(organization_id=org.id, name="Test Company", spend_tree_id=tree.id)
        s.add(company)
        s.commit()
        s.add(ErpIntegration(company_id=company.id, erp_type="fake",
                             connected_at=datetime.now(timezone.utc)))
        s.commit()
    return engine


def _summary(result: dict) -> dict:
    """The single integration's summary out of the per-integration result."""
    assert len(result) == 1, result
    summary = next(iter(result.values()))
    assert summary["status"] == "ok", summary
    return summary


def test_run_sync_end_to_end(sqlite_engine):
    summary = _summary(runner.run_sync())

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
        assert ok.level_1 == "Indirect"
        assert ok.level_2 == "Technology"
        assert ok.level_3 == "Cloud Infrastructure"
        # The tree is three levels deep, so there is no fourth to record.
        assert ok.level_4 is None
        assert ok.confidence is not None
        assert ok.rationale
        # The match resolves to a real node of the company's assigned tree.
        # This assertion used to read `is None` — not as a rule but as a symptom:
        # nothing seeded `spend_categories`, so the accepted assignment was null
        # on every line the pipeline ever produced.
        node = s.get(SpendCategory, ok.spend_category_id)
        assert node is not None and node.name == "Cloud Infrastructure"
        assert node.spend_tree_id == s.get(Company, ok.company_id).spend_tree_id
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
    runner.run_sync()

    # A human verifies the categorized line, correcting the account.
    with Session(sqlite_engine) as s:
        ln = s.exec(select(InvoiceLine).where(InvoiceLine.status == "ai_categorized")).one()
        ln.status = "verified"
        ln.account_code = "6610"
        s.add(ln)
        s.commit()
        line_id = ln.id

    # A re-sync must not re-categorize (overwrite) the verified line.
    runner.run_sync()
    with Session(sqlite_engine) as s:
        ln = s.get(InvoiceLine, line_id)
        assert ln.status == "verified"
        assert ln.account_code == "6610"


def test_a_company_with_no_spend_tree_still_ingests_its_ledger(sqlite_engine):
    """Categorization is skipped, the ledger lands, the watermark advances.

    A missing taxonomy is a settings gap, not an ERP failure. Stalling the
    ingest behind it would help nobody, and inventing categories from a built-in
    taxonomy the customer never chose would be worse than leaving them
    uncategorized: the wrong ones flow into every report and savings
    suggestion with nothing downstream able to tell they were guessed.
    """
    with Session(sqlite_engine) as s:
        company = s.exec(select(Company)).one()
        company.spend_tree_id = None
        s.add(company)
        s.commit()

    summary = _summary(runner.run_sync())

    assert summary["invoices"] == 2, "the ledger must still land"
    assert summary["lines"] == 2
    assert summary["line_status"] == {"uncategorized": 2}
    assert "no spend tree" in summary["categorization"]["skipped"]

    with Session(sqlite_engine) as s:
        state = s.exec(select(SyncState)).one()
        assert state.status == "idle", "not an integration failure"
        assert "no spend tree" in (state.error_message or "")
        assert state.last_invoice_date == date(2025, 8, 3), (
            "a skipped categorization must not hold the watermark back"
        )


def test_invoice_has_file_and_no_voucher_column(sqlite_engine):
    runner.run_sync()

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


def test_a_document_renamed_in_the_erp_keeps_its_file_row(sqlite_engine, monkeypatch):
    """The File's identity is the ERP's `file_ref`, not the label beside it.

    Keying on the name instead would mint a second row and orphan the first
    every time a customer renamed a file — or, as Billy did, the moment a
    connector started reporting a name it had previously left blank.
    """
    runner.run_sync()
    with Session(sqlite_engine) as s:
        before = s.exec(select(Invoice).where(Invoice.invoice_number == "INV1")).one()
        original_file_id = before.file_id
        assert s.exec(select(func.count()).select_from(File)).one() == 2

    # `_SCANS` is shared module state; monkeypatch restores it after the test.
    monkeypatch.setattr(_SCANS["V1"], "file_name", "renamed-by-the-customer.pdf")
    runner.run_sync()

    with Session(sqlite_engine) as s:
        after = s.exec(select(Invoice).where(Invoice.invoice_number == "INV1")).one()
        assert after.file_id == original_file_id
        assert s.get(File, original_file_id).filename == "renamed-by-the-customer.pdf"
        # Renamed, not duplicated: still one File per invoice scan.
        assert s.exec(select(func.count()).select_from(File)).one() == 2


def test_entries_link_to_invoice_via_voucher(sqlite_engine):
    runner.run_sync()

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


def test_a_posting_links_to_the_invoice_line_it_came_from(sqlite_engine):
    """The line id is derived from (invoice, line_erp_id), not matched.

    `_persist_invoices` builds the line's id from the same pair, so the two
    agree by construction rather than by resembling each other.
    """
    runner.run_sync()

    with Session(sqlite_engine) as s:
        e1 = s.exec(select(ErpEntry).where(ErpEntry.erp_entry_id == "E1")).one()
        line = s.get(InvoiceLine, e1.source_invoice_line_id)
        assert line is not None
        assert line.description == "Cloud server - monthly hosting"
        assert line.invoice_id == e1.source_invoice_id


def test_vat_and_payable_postings_link_to_no_line(sqlite_engine):
    """They belong to the whole invoice, so null is the right answer, not a gap."""
    runner.run_sync()

    with Session(sqlite_engine) as s:
        for erp_id in ("E2", "E3"):
            row = s.exec(select(ErpEntry).where(ErpEntry.erp_entry_id == erp_id)).one()
            assert row.source_invoice_line_id is None


def test_a_posting_naming_an_undelivered_line_is_kept_unlinked(sqlite_engine, monkeypatch):
    """A dangling FK would abort the sync over one posting; null does not."""
    original = _FakeConnector.fetch_entries

    def with_a_bad_reference(self, since=None, account_codes=None):
        rows = original(self, since=since, account_codes=account_codes)
        for row in rows:
            if row.erp_entry_id == "E1":
                row.source_line_erp_id = "does-not-exist"
        return rows

    monkeypatch.setattr(_FakeConnector, "fetch_entries", with_a_bad_reference)
    # Completes rather than raising on the FK.
    runner.run_sync()

    with Session(sqlite_engine) as s:
        e1 = s.exec(select(ErpEntry).where(ErpEntry.erp_entry_id == "E1")).one()
        assert e1.source_invoice_line_id is None
        # The posting itself is still persisted, not dropped.
        assert e1.source_invoice_id is not None


def test_entries_are_not_categorized(sqlite_engine):
    runner.run_sync()

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
    # The integration is reached via the account, not a direct column; the ledger
    # date is named accounting_date.
    assert "erp_integration_id" not in ErpEntry.__table__.columns
    assert "entry_date" not in ErpEntry.__table__.columns
    assert "accounting_date" in ErpEntry.__table__.columns


def _acct(session, code: str) -> ErpAccount:
    return session.exec(select(ErpAccount).where(ErpAccount.erp_account_code == code)).one()


def test_with_vat_seeded_from_erp(sqlite_engine):
    runner.run_sync()
    with Session(sqlite_engine) as s:
        assert _acct(s, "6010").with_vat is True   # expense account, with VAT
        assert _acct(s, "2100").with_vat is False   # balance-sheet, without VAT
        # New accounts default to enabled.
        assert _acct(s, "6010").sync_enabled is True


def test_a_customers_vat_setting_survives_a_resync(sqlite_engine):
    """The second writer.

    `refresh-accounts` is not the only thing that upserts accounts — the sync
    does too, on every run. Preserving the setting in only one of them makes it
    revert unpredictably, which is the hardest kind of bug to report.
    """
    runner.run_sync()
    with Session(sqlite_engine) as s:
        acct = _acct(s, "6010")
        assert acct.with_vat is True    # seeded from the ERP
        acct.with_vat = False           # the customer disagrees
        acct.sync_enabled = True
        s.add(acct)
        s.commit()

    runner.run_sync()

    with Session(sqlite_engine) as s:
        acct = _acct(s, "6010")
        assert acct.with_vat is False   # ours stands
        # ERP-owned metadata still refreshes.
        assert acct.erp_account_name == "Cloud Hosting & Infrastructure"


def test_disabled_account_yields_no_entries(sqlite_engine):
    # First sync populates accounts + entries (E1 posts to account 6010).
    runner.run_sync()
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

    runner.run_sync()
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
    first = _summary(runner.run_sync())
    second = _summary(runner.run_sync())
    assert first["vendors"] == second["vendors"]
    assert first["lines"] == second["lines"]
    assert first["entries"] == second["entries"]

    with Session(sqlite_engine) as s:
        assert s.exec(select(func.count()).select_from(Vendor)).one() == 1
        assert s.exec(select(func.count()).select_from(InvoiceLine)).one() == 2
        assert s.exec(select(func.count()).select_from(ErpEntry)).one() == 8
        assert s.exec(select(func.count()).select_from(File)).one() == 2


# -- lines the ERP has stopped stating ---------------------------------------
#
# A line's identity is `(invoice, line_erp_id)`, so a line the ERP re-issues
# under a new id arrives as a *second* row. Billy does exactly that when a bill
# line is re-coded to another account, which made seven invoices state their
# spend twice on the dev org before this was pruned.


def _invoice_lines(session, invoice_number: str) -> list[InvoiceLine]:
    invoice = session.exec(
        select(Invoice).where(Invoice.invoice_number == invoice_number)
    ).one()
    return list(session.exec(
        select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)
    ).all())


def _recode_v1_line(monkeypatch, line_erp_id: str = "1-recoded", code: str = "6020") -> None:
    """The ERP restates V1's only line under a new id, on a different account."""
    monkeypatch.setattr(_SCANS["V1"], "lines", [
        ErpInvoiceLineData(line_erp_id=line_erp_id,
                           description="Cloud server - monthly hosting",
                           amount=1000.0, native_account_code=code),
    ])


def test_a_line_the_erp_no_longer_states_is_removed(sqlite_engine, monkeypatch):
    """The replacement lands, and the row it replaced does not survive beside it.

    Keeping both is not a cosmetic duplicate: the invoice's lines then sum to
    twice its total, so it can never reconcile again and its spend is counted
    twice everywhere lines are summed.
    """
    runner.run_sync()
    with Session(sqlite_engine) as s:
        assert [ln.native_account_code for ln in _invoice_lines(s, "INV1")] == ["6010"]

    _recode_v1_line(monkeypatch)
    runner.run_sync()

    with Session(sqlite_engine) as s:
        assert [ln.native_account_code for ln in _invoice_lines(s, "INV1")] == ["6020"]


def test_a_posting_on_a_removed_line_is_unlinked_not_dangling(sqlite_engine, monkeypatch):
    """The posting outlives the line, pointing at no line — as extraction does.

    An `ErpEntry.source_invoice_line_id` left pointing at a deleted row is a
    dangling FK that aborts the sync on PostgreSQL, and re-pointing it at the
    replacement would be the amount-matching the derived link exists to refuse.
    """
    runner.run_sync()
    _recode_v1_line(monkeypatch)
    runner.run_sync()

    with Session(sqlite_engine) as s:
        entry = s.exec(select(ErpEntry).where(ErpEntry.erp_entry_id == "E1")).one()
        assert entry.source_invoice_line_id is None
        assert entry.source_invoice_id is not None  # the invoice link is untouched


def test_a_removed_line_leaves_its_values_in_the_audit_trail(sqlite_engine, monkeypatch):
    """The audit row is the only record the line ever existed."""
    runner.run_sync()
    with Session(sqlite_engine) as s:
        removed_id = _invoice_lines(s, "INV1")[0].id

    _recode_v1_line(monkeypatch)
    runner.run_sync()

    with Session(sqlite_engine) as s:
        # The line already carries an `ai_categorize` row from the first run;
        # the withdrawal is appended beside it, never in place of it.
        entry = s.exec(
            select(AuditLog).where(
                AuditLog.entity_id == removed_id,
                AuditLog.action == runner.WITHDRAWN_ACTION,
            )
        ).one()
        assert entry.entity_type == "invoice_line"
        assert entry.actor == "system"
        changed = {c["field"]: c["old"] for c in entry.changes}
        assert changed["amount"] == "1000.00"
        assert changed["native_account_code"] == "6010"


def test_a_human_added_line_is_never_pruned(sqlite_engine, monkeypatch):
    """A reviewer's own line is not the ERP's to withdraw.

    Splitting a stand-in means adding real lines beside it before deleting it,
    so a prune that removed every line the ERP did not state would delete the
    reviewer's work the moment the next sync ran.
    """
    runner.run_sync()
    with Session(sqlite_engine) as s:
        invoice = s.exec(select(Invoice).where(Invoice.invoice_number == "INV1")).one()
        s.add(InvoiceLine(company_id=invoice.company_id, invoice_id=invoice.id,
                          description="Split out by a reviewer", amount=Decimal("400.00"),
                          status="uncategorized", origin="human", sequence=1))
        s.commit()

    _recode_v1_line(monkeypatch)
    runner.run_sync()

    with Session(sqlite_engine) as s:
        origins = sorted(ln.origin for ln in _invoice_lines(s, "INV1"))
        assert origins == ["erp", "human"]


def test_withdrawing_a_line_recomputes_the_invoice_status(sqlite_engine, monkeypatch):
    """The rollup follows the lines that remain, not the ones that were there.

    The categorizer recomputes the rollup, but only for an invoice with pending
    lines — so an invoice whose *only* verified line is withdrawn, the rest
    already categorized, would otherwise keep claiming to be verified with no
    verified line left under it.
    """
    two_lines = [
        ErpInvoiceLineData(line_erp_id="1", description="Cloud server - monthly hosting",
                           amount=1000.0, native_account_code="6010"),
        ErpInvoiceLineData(line_erp_id="2", description="Cloud server - monthly hosting",
                           amount=1000.0, native_account_code="6010"),
    ]
    monkeypatch.setattr(_SCANS["V1"], "lines", two_lines)
    runner.run_sync()

    # One line verified, one left as the AI categorized it: the invoice rolls up
    # to "categorized", because not every line is verified yet.
    with Session(sqlite_engine) as s:
        first, _second = sorted(_invoice_lines(s, "INV1"), key=lambda ln: ln.sequence)
        first.status = "verified"
        s.add(first)
        s.commit()
        invoice = s.exec(select(Invoice).where(Invoice.invoice_number == "INV1")).one()
        recompute_invoice_status(s, invoice.id)
        s.commit()
        assert invoice.status == "categorized"

    # The ERP withdraws the unverified one. Every remaining line is verified, so
    # the invoice is now verified — but nothing is pending on it, so the
    # categorizer never revisits it and cannot be what notices.
    monkeypatch.setattr(_SCANS["V1"], "lines", two_lines[:1])
    runner.run_sync()

    with Session(sqlite_engine) as s:
        assert len(_invoice_lines(s, "INV1")) == 1
        invoice = s.exec(select(Invoice).where(Invoice.invoice_number == "INV1")).one()
        assert invoice.status == "verified"


def test_an_unchanged_resync_removes_nothing(sqlite_engine):
    """The prune fires on a line the ERP dropped, never on a steady state."""
    runner.run_sync()
    runner.run_sync()

    with Session(sqlite_engine) as s:
        assert s.exec(select(func.count()).select_from(InvoiceLine)).one() == 2
        withdrawn = s.exec(
            select(func.count()).select_from(AuditLog)
            .where(AuditLog.action == runner.WITHDRAWN_ACTION)
        ).one()
        assert withdrawn == 0


# -- currency conversion -----------------------------------------------------
#
# The fake ERP posts everything in DKK; the company reports in EUR. Rates come
# from a stub that records every call, so these tests can assert not only what
# was converted but how many lookups it cost.

_EUR_RATES = {"EUR": Decimal("1"), "DKK": Decimal("7.4600"), "USD": Decimal("1.0850")}


class _StubRates:
    """Serves the same published rates for any date, and counts the asking."""

    def __init__(self, rates=None, fail: bool = False):
        self.rates = _EUR_RATES if rates is None else rates
        self.fail = fail
        self.calls: list[date] = []

    def fetch(self, rate_date: date):
        self.calls.append(rate_date)
        return None if self.fail else (rate_date, dict(self.rates))


@pytest.fixture
def eur_company(sqlite_engine):
    """Point the seeded company at EUR, so its DKK postings must convert."""
    with Session(sqlite_engine) as s:
        company = s.exec(select(Company)).one()
        company.base_currency = "EUR"
        s.add(company)
        s.commit()
    return sqlite_engine


def _with_rates(monkeypatch, provider):
    """Give the runner an FX service backed by `provider` instead of the default."""
    monkeypatch.setattr(runner, "FxService", lambda session: FxService(session, provider))
    return provider


def test_sync_converts_into_the_companys_base_currency(eur_company, monkeypatch):
    _with_rates(monkeypatch, _StubRates())

    summary = _summary(runner.run_sync())

    assert summary["base_currency"] == "EUR"
    with Session(eur_company) as s:
        entry = s.exec(select(ErpEntry).where(ErpEntry.erp_entry_id == "E1")).one()
        assert entry.base_currency == "EUR"
        assert entry.fx_rate == Decimal("0.13404826")  # 1 / 7.46
        assert entry.base_debit_amount == Decimal("134.05")
        assert entry.fx_rate_date == date(2025, 7, 15)
        # The posting itself is untouched — it is the evidence, not a draft.
        assert entry.currency == "DKK"
        assert entry.debit_amount == Decimal("1000.00")


def test_an_invoice_and_its_lines_convert_at_the_invoices_date(eur_company, monkeypatch):
    _with_rates(monkeypatch, _StubRates())

    runner.run_sync()

    with Session(eur_company) as s:
        invoice = s.exec(select(Invoice).where(Invoice.invoice_number == "INV1")).one()
        assert invoice.base_total == Decimal("167.56")  # 1250.00 / 7.46
        assert invoice.base_tax == Decimal("33.51")
        assert invoice.fx_rate_date == date(2025, 7, 15)

        line = s.exec(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)).one()
        # A line has no date of its own: it must land on its invoice's rate.
        assert line.fx_rate == invoice.fx_rate
        assert line.fx_rate_date == invoice.fx_rate_date
        assert line.base_amount == Decimal("134.05")


def test_a_date_costs_one_rate_lookup_however_many_rows_share_it(eur_company, monkeypatch):
    provider = _with_rates(monkeypatch, _StubRates())

    runner.run_sync()

    # Six entries, two invoices and two lines span exactly two accounting dates.
    assert sorted(provider.calls) == [date(2025, 7, 15), date(2025, 8, 3)]


def test_a_posting_with_no_accounting_date_is_left_unconverted(eur_company, monkeypatch):
    _with_rates(monkeypatch, _StubRates())

    runner.run_sync()

    with Session(eur_company) as s:
        payment = s.exec(select(ErpEntry).where(ErpEntry.erp_entry_id == "E7")).one()
        assert payment.accounting_date is None
        assert payment.base_debit_amount is None
        assert payment.base_currency is None
        # Still fully persisted, and still carrying what the ERP posted.
        assert payment.debit_amount == Decimal("1250.00")


def test_a_currency_the_source_does_not_publish_is_left_unconverted(eur_company, monkeypatch):
    _with_rates(monkeypatch, _StubRates(rates={"EUR": Decimal("1"), "USD": Decimal("1.085")}))

    summary = _summary(runner.run_sync())

    assert summary["fx"]["converted"] == 0
    with Session(eur_company) as s:
        assert all(e.base_debit_amount is None for e in s.exec(select(ErpEntry)).all())
        assert all(e.debit_amount is not None or e.credit_amount is not None
                   for e in s.exec(select(ErpEntry)).all())


def test_a_dead_rate_provider_does_not_fail_the_sync(eur_company, monkeypatch):
    _with_rates(monkeypatch, _StubRates(fail=True))

    result = runner.run_sync()

    # Ledger data is not held hostage to FX: the integration still succeeds…
    summary = _summary(result)
    assert summary["entries"] == 8
    assert summary["fx"]["unconverted"] > 0
    with Session(eur_company) as s:
        # …the watermark still advances, so the next run is not stuck…
        assert s.exec(select(SyncState)).one().last_invoice_date == date(2025, 8, 3)
        # …and every row is there, simply unconverted.
        assert s.exec(select(func.count()).select_from(ErpEntry)).one() == 8
        assert all(e.base_currency is None for e in s.exec(select(ErpEntry)).all())


def test_a_later_run_fills_in_what_the_outage_missed(eur_company, monkeypatch):
    _with_rates(monkeypatch, _StubRates(fail=True))
    runner.run_sync()

    _with_rates(monkeypatch, _StubRates())
    runner.run_sync()

    with Session(eur_company) as s:
        entry = s.exec(select(ErpEntry).where(ErpEntry.erp_entry_id == "E1")).one()
        assert entry.base_debit_amount == Decimal("134.05")


def test_a_resync_reconverts_nothing(eur_company, monkeypatch):
    _with_rates(monkeypatch, _StubRates())
    runner.run_sync()
    with Session(eur_company) as s:
        before = {
            e.erp_entry_id: (e.base_debit_amount, e.fx_rate, e.fx_rate_date)
            for e in s.exec(select(ErpEntry)).all()
        }

    second = _with_rates(monkeypatch, _StubRates())
    summary = _summary(runner.run_sync())

    assert second.calls == []           # nothing re-fetched
    assert summary["fx"]["converted"] == 0
    assert summary["fx"]["unchanged"] > 0
    with Session(eur_company) as s:
        after = {
            e.erp_entry_id: (e.base_debit_amount, e.fx_rate, e.fx_rate_date)
            for e in s.exec(select(ErpEntry)).all()
        }
    assert after == before


def test_the_runner_never_sets_the_base_currency(eur_company, monkeypatch):
    _with_rates(monkeypatch, _StubRates())

    runner.run_sync()

    with Session(eur_company) as s:
        assert s.exec(select(Company)).one().base_currency == "EUR"


# -- The two account writers must agree on identity --------------------------


def test_the_runner_adopts_accounts_the_refresh_endpoint_created(sqlite_engine):
    """`refresh-accounts` and the runner both write this table.

    They used to disagree about identity — the endpoint keys on
    `(integration, code)` with an ordinary random id, the runner looked up a
    deterministic id by primary key — so a sync after a refresh inserted a
    second copy of the entire chart, and the two copies then drifted as each
    writer updated only its own.
    """
    with Session(sqlite_engine) as s:
        integration = s.exec(select(ErpIntegration)).one()
        # Exactly what the endpoint writes: natural key, random id, and a
        # customer setting the runner must not touch.
        s.add(ErpAccount(erp_integration_id=integration.id, erp_account_code="6010",
                         erp_account_name="Stale name", sync_enabled=False))
        s.commit()
        integration_id = integration.id

    runner.run_sync()

    with Session(sqlite_engine) as s:
        rows = s.exec(
            select(ErpAccount).where(
                ErpAccount.erp_integration_id == integration_id,
                ErpAccount.erp_account_code == "6010",
            )
        ).all()
        assert len(rows) == 1, "the runner duplicated an account the endpoint created"
        # It adopted the existing row: ERP metadata refreshed, the customer's
        # selection left alone.
        assert rows[0].erp_account_name != "Stale name"
        assert rows[0].sync_enabled is False


def test_running_the_sync_twice_does_not_duplicate_accounts(sqlite_engine):
    runner.run_sync()
    runner.run_sync()

    with Session(sqlite_engine) as s:
        codes = [a.erp_account_code for a in s.exec(select(ErpAccount)).all()]
        assert len(codes) == len(set(codes)), f"duplicate accounts: {codes}"
