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
from .grounding import ground_categorization
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
    def categorize(self):
        if self.state.skipped or self.state.errored:
            return
        try:
            inv = self.state.extracted
            descriptions = "; ".join(li.description for li in inv.line_items)
            query = f"{inv.vendor_name}: {descriptions}"
            # Deterministic RAG: retrieve candidates in code and let a toolless
            # agent pick one. This avoids the slow/unreliable agentic tool-call
            # loop; the chosen code is then validated against the real chart.
            candidates = retrieve_accounts(query, top_k=5)
            candidate_lines = "\n".join(
                f"- {c['account_code']} | {c['account_name']} | {c['category']} | {c['description']}"
                for c in candidates
            )
            agent = make_categorizer()
            result = agent.kickoff(
                "Choose the single best account for this invoice, using ONLY one of the "
                "candidate account codes listed below. Do not invent a code.\n\n"
                f"Invoice: {query}\n\nCandidate accounts:\n{candidate_lines}",
                response_format=CategorizedInvoice,
            )
            accounts_by_code = {a["account_code"]: a for a in load_accounts()}
            # If candidates is empty (index not built/populated), grounding cannot
            # snap and a fabricated code may pass through on a processed row; the
            # note records this. run_all builds the index first, so this is rare.
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
            # The flow itself crashed before record_to_ledger ran; still write a
            # row so every invoice is accounted for in the ledger.
            try:
                append_row(
                    build_ledger_row(
                        source_file=pdf.name,
                        skipped=False,
                        skip_reason="",
                        extracted=None,
                        verification=None,
                        categorized=None,
                        errored=True,
                        error_reason=f"flow crashed: {exc}",
                    ),
                    config.LEDGER_PATH,
                )
            except Exception:  # noqa: BLE001 - never let logging break the batch
                pass
            continue
        state = invoice_flow.state
        if state.skipped:
            print(f"  skipped: {state.skip_reason}")
        elif state.errored:
            print(f"  error: {state.error_reason}")
        elif state.categorized:
            c = state.categorized
            note = f" [{state.categorization_note}]" if state.categorization_note else ""
            print(f"  -> {c.account_code} {c.account_name} (confidence {c.confidence}){note}")
    print(f"Done. Ledger: {config.LEDGER_PATH}")
