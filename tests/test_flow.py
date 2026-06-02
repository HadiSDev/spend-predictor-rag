import csv

from spend_predictor import config, flow
from spend_predictor.models import (
    AccountChoice,
    ExtractedInvoice,
    LineItem,
    VerificationResult,
)


class _FakeResult:
    def __init__(self, pydantic):
        self.pydantic = pydantic


class _FakeAgent:
    def __init__(self, pydantic):
        self._pydantic = pydantic

    def kickoff(self, *args, **kwargs):
        return _FakeResult(self._pydantic)


def _read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _install_fakes(monkeypatch, ledger_path):
    monkeypatch.setattr(config, "LEDGER_PATH", str(ledger_path))
    extracted = ExtractedInvoice(
        vendor_name="Acme Cloud",
        invoice_number="INV-1",
        invoice_date="2026-05-01",
        currency="USD",
        line_items=[LineItem(description="cloud hosting", amount=100.0)],
        subtotal=100.0,
        tax=0.0,
        total=100.0,
    )
    verification = VerificationResult(arithmetic_ok=True, discrepancies=[], notes=None)
    choice = AccountChoice(
        account_code="6010", account_name="Cloud Hosting", level1="Direct", confidence=0.9, rationale="ok"
    )
    monkeypatch.setattr(flow, "make_extractor", lambda: _FakeAgent(extracted))
    monkeypatch.setattr(flow, "make_verifier", lambda: _FakeAgent(verification))
    monkeypatch.setattr(flow, "make_categorizer", lambda: _FakeAgent(choice))
    account = {
        "account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
        "level2": "Technology", "level3": "Cloud Infrastructure", "description": "cloud servers and hosting",
    }
    monkeypatch.setattr(flow, "retrieve_accounts", lambda query, top_k=5: [account])
    monkeypatch.setattr(flow, "load_accounts", lambda: [account])
    monkeypatch.setattr(flow, "get_product_context", lambda line_items, vendor_name: "")


def test_flow_writes_processed_row(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.csv"
    _install_fakes(monkeypatch, ledger)
    monkeypatch.setattr(flow, "extract_text", lambda p: "INVOICE Acme Cloud total 100")

    flow.InvoiceFlow().kickoff(inputs={"pdf_path": "/x/sample.pdf"})

    rows = _read(ledger)
    assert len(rows) == 1
    assert rows[0]["status"] == "processed"
    assert rows[0]["source_file"] == "sample.pdf"
    assert rows[0]["account_code"] == "6010"
    assert rows[0]["level1"] == "Direct"
    assert rows[0]["level2"] == "Technology"
    assert rows[0]["account_name"] == "Cloud Hosting & Infrastructure"


def test_flow_snaps_hallucinated_account_code(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.csv"
    _install_fakes(monkeypatch, ledger)
    monkeypatch.setattr(flow, "extract_text", lambda p: "INVOICE Acme Cloud total 100")
    # categorizer fabricates a code that is not in the chart
    bogus = AccountChoice(
        account_code="9999", account_name="Made Up", level1="Indirect", confidence=0.95, rationale="hallucinated"
    )
    monkeypatch.setattr(flow, "make_categorizer", lambda: _FakeAgent(bogus))

    flow.InvoiceFlow().kickoff(inputs={"pdf_path": "/x/sample.pdf"})

    rows = _read(ledger)
    assert rows[0]["account_code"] == "6010"  # snapped to the top retrieved candidate
    assert "9999" in rows[0]["notes"] and "6010" in rows[0]["notes"]


def test_flow_records_error_row_on_stage_failure(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.csv"
    _install_fakes(monkeypatch, ledger)
    monkeypatch.setattr(flow, "extract_text", lambda p: "INVOICE Acme Cloud total 100")

    class _RaisingAgent:
        def kickoff(self, *args, **kwargs):
            raise RuntimeError("model timeout")

    monkeypatch.setattr(flow, "make_verifier", lambda: _RaisingAgent())

    flow.InvoiceFlow().kickoff(inputs={"pdf_path": "/x/sample.pdf"})

    rows = _read(ledger)
    assert len(rows) == 1
    assert rows[0]["status"] == "error"
    assert "verify failed" in rows[0]["notes"]
    assert "model timeout" in rows[0]["notes"]
    assert rows[0]["account_code"] == ""


def test_flow_skips_empty_pdf_and_does_not_call_agents(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.csv"
    _install_fakes(monkeypatch, ledger)
    monkeypatch.setattr(flow, "extract_text", lambda p: "")

    def _boom():
        raise AssertionError("agents must not run for skipped invoices")

    monkeypatch.setattr(flow, "make_extractor", lambda: _boom())
    monkeypatch.setattr(flow, "make_verifier", lambda: _boom())
    monkeypatch.setattr(flow, "make_categorizer", lambda: _boom())

    flow.InvoiceFlow().kickoff(inputs={"pdf_path": "/x/blank.pdf"})

    rows = _read(ledger)
    assert len(rows) == 1
    assert rows[0]["status"] == "skipped"
    assert rows[0]["notes"] == "empty PDF text"
    assert rows[0]["account_code"] == ""


def test_flow_skips_on_pdf_error(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.csv"
    _install_fakes(monkeypatch, ledger)

    def _raise(p):
        raise ValueError("not a pdf")

    monkeypatch.setattr(flow, "extract_text", _raise)

    flow.InvoiceFlow().kickoff(inputs={"pdf_path": "/x/broken.pdf"})

    rows = _read(ledger)
    assert rows[0]["status"] == "skipped"
    assert "not a pdf" in rows[0]["notes"]


def test_flow_uses_buyer_and_product_context(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.csv"
    _install_fakes(monkeypatch, ledger)
    monkeypatch.setattr(flow, "extract_text", lambda p: "INVOICE Acme Cloud total 100")

    seen = {}

    def _fake_product_context(line_items, vendor_name):
        seen["called"] = True
        return "PRODUCTS: cloud hosting"

    monkeypatch.setattr(flow, "get_product_context", _fake_product_context)

    captured = {}

    class _CapturingAgent:
        def kickoff(self, prompt, **kwargs):
            captured["prompt"] = prompt
            from spend_predictor.models import AccountChoice
            return type("R", (), {"pydantic": AccountChoice(
                account_code="6010", account_name="Cloud", level1="Direct", confidence=0.9, rationale="ok")})()

    monkeypatch.setattr(flow, "make_categorizer", lambda: _CapturingAgent())

    flow.InvoiceFlow().kickoff(inputs={"pdf_path": "/x/sample.pdf", "buyer_context": "Acme is a SaaS company."})

    assert seen.get("called") is True
    assert "Acme is a SaaS company." in captured["prompt"]
    assert "PRODUCTS: cloud hosting" in captured["prompt"]
