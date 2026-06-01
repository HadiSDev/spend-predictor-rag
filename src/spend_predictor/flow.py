"""The invoice-processing Flow and the run-all entry point."""
from __future__ import annotations

from pathlib import Path

from crewai.flow.flow import Flow, listen, start

from . import config
from .agents import make_categorizer, make_extractor, make_verifier
from .ledger import append_row, build_ledger_row
from .models import (
    CategorizedInvoice,
    ExtractedInvoice,
    InvoiceState,
    VerificationResult,
)
from .pdf_loader import extract_text
from .rag.indexer import build_index


class InvoiceFlow(Flow[InvoiceState]):
    """Process a single invoice: load -> extract -> verify -> categorize -> ledger."""

    @start()
    def load_invoice(self):
        try:
            text = extract_text(self.state.pdf_path)
        except Exception as exc:  # noqa: BLE001 - any parse failure means skip
            self.state.skipped = True
            self.state.skip_reason = f"PDF parse error: {exc}"
            return
        if not text.strip():
            self.state.skipped = True
            self.state.skip_reason = "empty PDF text"
            return
        self.state.invoice_text = text

    @listen(load_invoice)
    def extract(self):
        if self.state.skipped:
            return
        agent = make_extractor()
        result = agent.kickoff(
            "Extract the structured invoice data from the following invoice text. "
            "Leave any missing field null.\n\n" + self.state.invoice_text,
            response_format=ExtractedInvoice,
        )
        self.state.extracted = result.pydantic

    @listen(extract)
    def verify(self):
        if self.state.skipped:
            return
        agent = make_verifier()
        result = agent.kickoff(
            "Verify the arithmetic of this extracted invoice and list any "
            "discrepancies.\n\n" + self.state.extracted.model_dump_json(indent=2),
            response_format=VerificationResult,
        )
        self.state.verification = result.pydantic

    @listen(verify)
    def categorize(self):
        if self.state.skipped:
            return
        inv = self.state.extracted
        descriptions = "; ".join(li.description for li in inv.line_items)
        query = f"{inv.vendor_name}: {descriptions}"
        agent = make_categorizer()
        result = agent.kickoff(
            "Categorize this invoice to the single best account in the corporate "
            "chart of accounts. Use the chart_of_accounts_search tool to find "
            f"candidates for: {query}. Choose only from the returned accounts.",
            response_format=CategorizedInvoice,
        )
        self.state.categorized = result.pydantic

    @listen(categorize)
    def record_to_ledger(self):
        row = build_ledger_row(
            source_file=Path(self.state.pdf_path).name,
            skipped=self.state.skipped,
            skip_reason=self.state.skip_reason,
            extracted=self.state.extracted,
            verification=self.state.verification,
            categorized=self.state.categorized,
        )
        append_row(row, config.LEDGER_PATH)


def run_all() -> None:
    """Process every PDF in the invoices directory into the ledger."""
    invoices_dir = Path(config.INVOICES_DIR)
    pdfs = sorted(invoices_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {invoices_dir}")
        return

    build_index()  # ensure the RAG index exists (no-op if already built)

    for pdf in pdfs:
        print(f"Processing {pdf.name} ...")
        invoice_flow = InvoiceFlow()
        try:
            invoice_flow.kickoff(inputs={"pdf_path": str(pdf)})
        except Exception as exc:  # noqa: BLE001 - keep processing remaining invoices
            print(f"  ERROR: {exc}")
            continue
        state = invoice_flow.state
        if state.skipped:
            print(f"  skipped: {state.skip_reason}")
        elif state.categorized:
            c = state.categorized
            print(f"  -> {c.account_code} {c.account_name} (confidence {c.confidence})")
    print(f"Done. Ledger: {config.LEDGER_PATH}")
