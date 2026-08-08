"""The sync runner: what it syncs, where it gets credentials, how it fails."""
from __future__ import annotations

import pytest
from sqlmodel import Session, select, func

from ai_api.sync import runner
from web_api.db.models import (
    Company,
    ErpAccount,
    ErpEntry,
    ErpIntegration,
    Invoice,
    InvoiceLine,
    Organization,
    SyncState,
)


# What one tenant's worth of `FakeConnector` data persists to. Pinned before the
# refactor so "the pipeline still does the same thing" is checkable afterwards,
# not merely asserted.
EXPECTED = {
    "vendors": 1,
    "invoices": 1,
    "lines": 1,
    "entries": 3,
    "entries_linked": 2,
    "accounts": 2,
    "accounts_enabled": 2,
}


def _counts(engine, company_id: str) -> dict:
    with Session(engine) as s:
        def n(model, cond):
            return s.exec(select(func.count()).select_from(model).where(cond)).one()

        return {
            "invoices": n(Invoice, Invoice.company_id == company_id),
            "lines": n(InvoiceLine, InvoiceLine.company_id == company_id),
            "entries": n(ErpEntry, ErpEntry.company_id == company_id),
        }


def test_pipeline_persists_a_tenants_data(engine, make_tenant):
    """Baseline: one connected integration syncs into its own company."""
    tenant = make_tenant("Acme")

    result = runner.run_sync()

    summary = result[tenant["integration_id"]]
    assert summary["status"] == "ok"
    for key, value in EXPECTED.items():
        assert summary[key] == value, key
    assert _counts(engine, tenant["company_id"]) == {"invoices": 1, "lines": 1, "entries": 3}


# --- Work discovery ---------------------------------------------------------


def test_every_connected_integration_is_synced(engine, make_tenant):
    a = make_tenant("Acme")
    b = make_tenant("Beta")

    result = runner.run_sync()

    assert set(result) == {a["integration_id"], b["integration_id"]}
    assert all(r["status"] == "ok" for r in result.values())
    # Each tenant's data lands in its own company, not pooled.
    assert _counts(engine, a["company_id"])["entries"] == 3
    assert _counts(engine, b["company_id"])["entries"] == 3


def test_a_company_created_through_the_api_needs_no_code_change(engine, make_tenant):
    """The whole point: the runner discovers it, nothing names it."""
    tenant = make_tenant("Created In Settings")

    result = runner.run_sync()

    assert result[tenant["integration_id"]]["status"] == "ok"
    with Session(engine) as s:
        entry = s.exec(select(ErpEntry)).first()
        company = s.get(Company, entry.company_id)
        assert company.id == tenant["company_id"]
        assert company.organization_id == tenant["org_id"]


def test_disconnected_integration_is_skipped_and_returns_on_reconnect(engine, make_tenant):
    tenant = make_tenant("Acme", connected=False)

    assert runner.run_sync() == {}

    with Session(engine) as s:
        integration = s.get(ErpIntegration, tenant["integration_id"])
        integration.disconnected_at = None
        s.add(integration)
        s.commit()

    assert set(runner.run_sync()) == {tenant["integration_id"]}


def test_an_inactive_company_is_still_polled(engine, make_tenant):
    """Deliberately uncoupled: deactivation is an API concern, not a sync one."""
    tenant = make_tenant("Acme")
    with Session(engine) as s:
        company = s.get(Company, tenant["company_id"])
        company.is_active = False
        s.add(company)
        s.commit()

    assert runner.run_sync()[tenant["integration_id"]]["status"] == "ok"


def test_the_runner_never_invents_a_tenant(engine):
    assert runner.run_sync() == {}

    with Session(engine) as s:
        assert s.exec(select(func.count()).select_from(Organization)).one() == 0
        assert s.exec(select(func.count()).select_from(Company)).one() == 0
        assert s.exec(select(func.count()).select_from(ErpIntegration)).one() == 0


def test_unknown_integration_id_is_rejected_and_creates_nothing(engine, make_tenant):
    make_tenant("Acme")

    with pytest.raises(ValueError, match="No connected ERP integration"):
        runner.run_sync(integration_id="does-not-exist")

    with Session(engine) as s:
        assert s.exec(select(func.count()).select_from(Company)).one() == 1
        assert s.exec(select(func.count()).select_from(ErpEntry)).one() == 0


def test_one_integration_can_be_re_run_alone(engine, make_tenant):
    a = make_tenant("Acme")
    b = make_tenant("Beta")

    result = runner.run_sync(integration_id=b["integration_id"])

    assert set(result) == {b["integration_id"]}
    assert _counts(engine, a["company_id"])["entries"] == 0


# --- Credentials ------------------------------------------------------------


def test_stored_credentials_reach_the_connector(engine, make_tenant, fake_connector, enc_key):
    make_tenant("Acme", credentials={"base_url": "http://real", "api_key": "s3cret"})

    runner.run_sync()

    assert {"base_url": "http://real", "api_key": "s3cret"} in fake_connector.seen_configs


def test_no_credential_row_means_connector_defaults(engine, make_tenant, fake_connector):
    """The normal case for a connector whose fields all have defaults."""
    tenant = make_tenant("Acme", credentials=None)

    result = runner.run_sync()

    assert result[tenant["integration_id"]]["status"] == "ok"
    assert fake_connector.seen_configs == [{}]


def test_undecryptable_credentials_fail_only_their_own_integration(
    engine, make_tenant, enc_key, monkeypatch
):
    broken = make_tenant("Broken", credentials={"api_key": "x"})
    healthy = make_tenant("Healthy", credentials=None)

    # Rotate the key out from under the stored token.
    from cryptography.fernet import Fernet
    from web_api import config as web_config

    monkeypatch.setattr(web_config, "WEB_API_CREDENTIAL_ENC_KEY", Fernet.generate_key().decode())

    result = runner.run_sync()

    assert result[broken["integration_id"]]["status"] == "error"
    assert "WEB_API_CREDENTIAL_ENC_KEY" in result[broken["integration_id"]]["error"]
    assert result[healthy["integration_id"]]["status"] == "ok"


# --- Failure isolation ------------------------------------------------------


def test_an_unreachable_erp_does_not_stop_the_others(engine, make_tenant, fake_connector):
    """Whichever is reached first, the other still gets its data."""
    make_tenant("First")
    make_tenant("Second")

    # Unreachable on the first attempt only.
    original = fake_connector.test_connection
    attempts = {"n": 0}

    def flaky(self):
        attempts["n"] += 1
        return attempts["n"] > 1

    fake_connector.test_connection = flaky
    try:
        result = runner.run_sync()
    finally:
        fake_connector.test_connection = original

    statuses = sorted(r["status"] for r in result.values())
    assert statuses == ["error", "ok"]
    failed = next(r for r in result.values() if r["status"] == "error")
    synced = next(r for r in result.values() if r["status"] == "ok")
    assert "Could not reach" in failed["error"]
    assert _counts(engine, synced["company_id"])["entries"] == 3
    # The failed one persisted nothing — it never got past the connection check.
    assert _counts(engine, failed["company_id"])["entries"] == 0


def test_a_failure_is_recorded_on_its_own_sync_state(engine, make_tenant, fake_connector):
    tenant = make_tenant("Acme")
    fake_connector.reachable = False

    runner.run_sync()

    with Session(engine) as s:
        state = s.exec(
            select(SyncState).where(SyncState.erp_integration_id == tenant["integration_id"])
        ).one()
        assert state.status == "error"
        assert "Could not reach" in state.error_message


def test_earlier_tenants_data_survives_a_later_failure(engine, make_tenant, fake_connector):
    make_tenant("First")
    make_tenant("Second")

    # Blow up on whichever integration is processed second.
    calls = {"n": 0}
    original = fake_connector.fetch_entries

    def fail_on_second(self, since=None, account_codes=None):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("fake ERP blew up mid-fetch")
        return original(self, since=since, account_codes=account_codes)

    fake_connector.fetch_entries = fail_on_second
    try:
        result = runner.run_sync()
    finally:
        fake_connector.fetch_entries = original

    assert sorted(r["status"] for r in result.values()) == ["error", "ok"]
    synced = next(r for r in result.values() if r["status"] == "ok")
    # Committed as it went, so the later failure cannot take it back.
    assert _counts(engine, synced["company_id"])["entries"] == 3


# --- Watermarks -------------------------------------------------------------


def test_second_run_fetches_from_the_recorded_watermark(engine, make_tenant, fake_connector):
    from datetime import date

    make_tenant("Acme")
    runner.run_sync()
    assert fake_connector.seen_since == [None]

    fake_connector.seen_since = []
    runner.run_sync()

    # The fake connector's only invoice is dated 2026-03-02.
    assert fake_connector.seen_since == [date(2026, 3, 2)]


def test_each_integration_uses_its_own_watermark(engine, make_tenant, fake_connector):
    from datetime import date

    make_tenant("Acme")
    runner.run_sync()          # Acme now has a watermark
    make_tenant("Beta")        # Beta has none

    fake_connector.seen_since = []
    runner.run_sync()

    assert sorted(fake_connector.seen_since, key=lambda d: (d is not None, d)) == [
        None, date(2026, 3, 2)
    ]


def test_an_explicit_since_overrides_every_watermark(engine, make_tenant, fake_connector):
    from datetime import date

    make_tenant("Acme")
    runner.run_sync()

    fake_connector.seen_since = []
    runner.run_sync(since=date(2020, 1, 1))

    assert fake_connector.seen_since == [date(2020, 1, 1)]


def test_a_failed_sync_does_not_advance_the_watermark(engine, make_tenant, fake_connector):
    from datetime import date

    tenant = make_tenant("Acme")
    runner.run_sync()

    fake_connector.reachable = False
    runner.run_sync()

    with Session(engine) as s:
        state = s.exec(
            select(SyncState).where(SyncState.erp_integration_id == tenant["integration_id"])
        ).one()
        assert state.status == "error"
        assert state.last_invoice_date == date(2026, 3, 2)  # unchanged, not reset


# --- CLI --------------------------------------------------------------------


def test_cli_on_an_empty_database_exits_zero(engine, capsys):
    assert runner.main([]) == 0
    assert "Nothing to sync" in capsys.readouterr().out


def test_cli_exits_non_zero_when_an_integration_failed(engine, make_tenant, fake_connector):
    make_tenant("Acme")
    fake_connector.reachable = False

    assert runner.main([]) == 1


def test_cli_reports_each_integration(engine, make_tenant, capsys):
    a = make_tenant("Acme")
    b = make_tenant("Beta")

    assert runner.main([]) == 0

    out = capsys.readouterr().out
    assert a["integration_id"] in out
    assert b["integration_id"] in out


def test_cli_rejects_an_unknown_integration_id(engine, make_tenant):
    make_tenant("Acme")
    with pytest.raises(SystemExit):
        runner.main(["--integration-id", "nope"])
