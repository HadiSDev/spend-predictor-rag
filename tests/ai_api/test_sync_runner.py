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



# --- What the categorizer is actually told ----------------------------------
#
# These go through `run_sync` on purpose. Every other categorizer test builds a
# `LineContext` by hand, which is precisely how the `item_name` migration moved
# a line's text out from under the prompt without a single test turning red: the
# line kept its words, the model stopped being given them, and the only place it
# showed was a rationale saying "no description of the goods or services
# provided". A mapping nothing exercises is a mapping nothing protects.
#
# Every assertion is made against the *facts* half of the prompt, never the
# whole thing. The candidate list quotes each node's description, so asserting
# on the full prompt passes on text the categorizer read off the taxonomy — the
# first version of this test did exactly that and passed against the bug.


@pytest.fixture
def prompts(monkeypatch):
    """Capture every prompt the categorizer would send, and answer candidate 1.

    Patches the module-level default completion rather than passing a `complete`
    seam, because the seam is exactly what the runner does *not* use — the point
    is to observe the real call path.
    """
    from ai_api.sync import llm_categorizer

    seen: list[str] = []

    def _capture(prompt: str) -> str:
        seen.append(prompt)
        return '{"choice": 1, "confidence": 0.9, "rationale": "stub"}'

    monkeypatch.setattr(llm_categorizer, "_default_complete", _capture)
    return seen


def _facts(prompts: list[str]) -> str:
    """The part of each prompt that describes the line, never the candidates."""
    assert prompts, "no line was categorized, so this test proves nothing"
    return "\n".join(p.split("Categories:", 1)[0] for p in prompts)


def _with_default_tree(engine, company_id: str) -> None:
    """Assign the organization's default tree, as `POST /companies` would."""
    from web_api.spend_trees import service

    with Session(engine) as s:
        company = s.get(Company, company_id)
        tree = service.ensure_default_tree(s, company.organization_id)
        company.spend_tree_id = tree.id
        s.add(company)
        s.commit()


def _synced_with(engine, make_tenant, fake_connector, line, **invoice) -> None:
    """Sync one tenant whose single invoice carries ``line``."""
    from datetime import date as _date

    from web_api.connectors.base import ErpInvoiceData

    tenant = make_tenant("Acme")
    _with_default_tree(engine, tenant["company_id"])
    fake_connector.scan = ErpInvoiceData(
        erp_id="INV-1", vendor_erp_id="V-1", vendor_name="Contoso ApS",
        invoice_number="2026-001", invoice_date=_date(2026, 3, 2), currency="DKK",
        total=1000.0, tax=200.0, voucher_id="V1", lines=[line], **invoice,
    )
    runner.run_sync()


def test_the_line_item_name_reaches_the_prompt(engine, make_tenant, fake_connector, prompts):
    """The connector states one text, the runner stores it as `item_name`, and
    the model must be shown it. The whole chain, or none of it is pinned."""
    from web_api.connectors.base import ErpInvoiceLineData

    _synced_with(engine, make_tenant, fake_connector, ErpInvoiceLineData(
        line_erp_id="L-1", description="DSB 1' Commute20", amount=800.0,
        native_account_code="6010",
    ))

    assert "DSB 1' Commute20" in _facts(prompts), (
        "the line's item name never reached the model:\n" + "\n---\n".join(prompts)
    )


def test_a_description_beside_a_name_reaches_the_prompt(
    engine, make_tenant, fake_connector, prompts
):
    """Both fields, both meanings. A coalesce would drop whichever came second."""
    from web_api.connectors.base import ErpInvoiceLineData

    _synced_with(engine, make_tenant, fake_connector, ErpInvoiceLineData(
        line_erp_id="L-1", item_name="Commuter pass",
        description="Roskilde to Odense, 2 months", amount=800.0,
        native_account_code="6010",
    ))

    facts = _facts(prompts)
    assert "Commuter pass" in facts
    assert "Roskilde to Odense, 2 months" in facts


def test_the_accounts_own_name_reaches_the_prompt(
    engine, make_tenant, fake_connector, prompts
):
    """A bare account code is not a statement of what was bought.
    "Cloud Hosting" is; on a posting-derived line it is often the only one."""
    from web_api.connectors.base import ErpInvoiceLineData

    _synced_with(engine, make_tenant, fake_connector, ErpInvoiceLineData(
        line_erp_id="L-1", description="Uspecificeret", amount=800.0,
        native_account_code="6010",
    ))

    facts = _facts(prompts)
    assert "6010" in facts and "Cloud Hosting" in facts


def test_the_supplier_reaches_the_prompt(engine, make_tenant, fake_connector, prompts):
    from web_api.connectors.base import ErpInvoiceLineData

    _synced_with(engine, make_tenant, fake_connector, ErpInvoiceLineData(
        line_erp_id="L-1", description="Uspecificeret", amount=800.0,
        native_account_code="6010",
    ))

    assert "Contoso ApS" in _facts(prompts)
