"""The invoice-processing Flow and the run-all entry point."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from crewai.flow.flow import Flow, listen, start

from . import config
from .agents import make_categorizer, make_extractor, make_verifier
from .grounding import ground_categorization
from .ledger import append_row, build_ledger_row
from .web_context import get_buyer_context, get_product_context
from .models import (
    AccountChoice,
    ExtractedInvoice,
    InvoiceState,
    VerificationResult,
)
from .pdf_loader import extract_text
from .rag.indexer import build_index, load_accounts, retrieve_accounts


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
        if self.state.skipped or self.state.errored:
            return
        try:
            agent = make_extractor()
            result = agent.kickoff(
                "Extract the structured invoice data from the following invoice text. "
                "Leave any missing field null.\n\n" + self.state.invoice_text,
                response_format=ExtractedInvoice,
            )
            self.state.extracted = result.pydantic
        except Exception as exc:  # noqa: BLE001 - record and move on
            self.state.errored = True
            self.state.error_reason = f"extract failed: {exc}"

    @listen(extract)
    def verify(self):
        if self.state.skipped or self.state.errored:
            return
        try:
            agent = make_verifier()
            result = agent.kickoff(
                "Verify the arithmetic of this extracted invoice and list any "
                "discrepancies.\n\n" + self.state.extracted.model_dump_json(indent=2),
                response_format=VerificationResult,
            )
            self.state.verification = result.pydantic
        except Exception as exc:  # noqa: BLE001 - record and move on
            self.state.errored = True
            self.state.error_reason = f"verify failed: {exc}"

    @listen(verify)
    def research_products(self):
        if self.state.skipped or self.state.errored:
            return
        try:
            inv = self.state.extracted
            self.state.product_context = get_product_context(inv.line_items, inv.vendor_name)
        except Exception:  # noqa: BLE001 - product context is best-effort
            self.state.product_context = ""

    @listen(research_products)
    def categorize(self):
        if self.state.skipped or self.state.errored:
            return
        try:
            inv = self.state.extracted
            descriptions = "; ".join(li.description for li in inv.line_items)
            query = f"{inv.vendor_name}: {descriptions}"
            candidates = retrieve_accounts(query, top_k=5)
            candidate_lines = "\n".join(
                f"- {c['account_code']} | {c['level2']} > {c['level3']} > {c['account_name']} | {c['description']}"
                for c in candidates
            )
            line_items = "\n".join(
                f"- {li.description} (qty={li.quantity}, amount={li.amount})"
                for li in inv.line_items
            )
            agent = make_categorizer()
            result = agent.kickoff(
                "Categorize this invoice. Choose ONE candidate account code and judge "
                "Direct vs Indirect from the buyer context and line items.\n\n"
                f"Buyer context:\n{self.state.buyer_context or '(none)'}\n\n"
                f"Product context:\n{self.state.product_context or '(none)'}\n\n"
                f"Invoice line items:\n{line_items}\n\n"
                f"Candidate accounts:\n{candidate_lines}",
                response_format=AccountChoice,
            )
            accounts_by_code = {a["account_code"]: a for a in load_accounts()}
            grounded, note = ground_categorization(
                result.pydantic, candidates, accounts_by_code
            )
            self.state.categorized = grounded
            self.state.categorization_note = note
        except Exception as exc:  # noqa: BLE001 - record and move on
            self.state.errored = True
            self.state.error_reason = f"categorize failed: {exc}"

    @listen(categorize)
    def record_to_ledger(self):
        row = build_ledger_row(
            source_file=Path(self.state.pdf_path).name,
            skipped=self.state.skipped,
            skip_reason=self.state.skip_reason,
            extracted=self.state.extracted,
            verification=self.state.verification,
            categorized=self.state.categorized,
            categorization_note=self.state.categorization_note,
            errored=self.state.errored,
            error_reason=self.state.error_reason,
            buyer_name=config.BUYER_NAME,
        )
        append_row(row, config.LEDGER_PATH)


def _process_invoice(pdf: Path, buyer_context: str) -> str:
    """Run one invoice through the flow and return a one-line summary.

    Each flow writes its own ledger row (the write is serialized in
    ``append_row``), so this is safe to call concurrently across invoices.
    """
    invoice_flow = InvoiceFlow()
    try:
        invoice_flow.kickoff(
            inputs={"pdf_path": str(pdf), "buyer_context": buyer_context}
        )
    except Exception as exc:  # noqa: BLE001 - keep processing remaining invoices
        try:
            append_row(
                build_ledger_row(
                    source_file=pdf.name, skipped=False, skip_reason="",
                    extracted=None, verification=None, categorized=None,
                    errored=True, error_reason=f"flow crashed: {exc}",
                    buyer_name=config.BUYER_NAME,
                ),
                config.LEDGER_PATH,
            )
        except Exception:  # noqa: BLE001
            pass
        return f"{pdf.name}: ERROR {exc}"

    state = invoice_flow.state
    if state.skipped:
        return f"{pdf.name}: skipped ({state.skip_reason})"
    if state.errored:
        return f"{pdf.name}: error ({state.error_reason})"
    if state.categorized:
        c = state.categorized
        note = f" [{state.categorization_note}]" if state.categorization_note else ""
        return f"{pdf.name}: {c.account_code} {c.account_name} (confidence {c.confidence}){note}"
    return f"{pdf.name}: done"


def run_all() -> None:
    """Process every PDF in the invoices directory into the ledger."""
    invoices_dir = Path(config.INVOICES_DIR)
    pdfs = sorted(invoices_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {invoices_dir}")
        return

    build_index()  # ensure the RAG index exists (no-op if already built)

    try:
        buyer_context = get_buyer_context()
    except Exception as exc:  # noqa: BLE001 - degrade to no buyer context
        print(f"  (buyer context unavailable: {exc})")
        buyer_context = ""

    workers = max(1, min(config.INVOICE_CONCURRENCY, len(pdfs)))
    print(f"Processing {len(pdfs)} invoice(s) with concurrency {workers} ...")
    if workers == 1:
        for pdf in pdfs:
            print(f"  {_process_invoice(pdf, buyer_context)}")
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for summary in executor.map(
                lambda pdf: _process_invoice(pdf, buyer_context), pdfs
            ):
                print(f"  {summary}")
    print(f"Done. Ledger: {config.LEDGER_PATH}")
