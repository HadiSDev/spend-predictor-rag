import csv

from spend_predictor import config, flow
from spend_predictor.models import (
    CategorizedInvoice,
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
    categorized = CategorizedInvoice(
        account_code="6010", account_name="Cloud Hosting", category="IT", confidence=0.9, rationale="ok"
    )
    monkeypatch.setattr(flow, "make_extractor", lambda: _FakeAgent(extracted))
    monkeypatch.setattr(flow, "make_verifier", lambda: _FakeAgent(verification))
    monkeypatch.setattr(flow, "make_categorizer", lambda: _FakeAgent(categorized))


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


def test_flow_skips_empty_pdf_and_does_not_call_agents(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.csv"
    _install_fakes(monkeypatch, ledger)
    monkeypatch.setattr(flow, "extract_text", lambda p: "")

    def _boom():
        raise AssertionError("agents must not run for skipped invoices")

    monkeypatch.setattr(flow, "make_extractor", lambda: _boom())

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
