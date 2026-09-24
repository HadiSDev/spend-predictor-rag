## 1. Baseline, before anything changes

- [x] 1.1 Dry-run extraction over all 28 invoices with a script that writes nothing, recording per invoice: line count, line sum, posted total, posted tax, and the current accept/reject verdict. Save as `baseline.md` in the change folder. Every later claim about improvement is measured against this file.
- [x] 1.2 From the baseline, record which of the six `failed` invoices state a totals block at all — that is the population this change can help, and it is currently a guess for five of them.

## 2. Read what the document says about itself

- [x] 2.1 Write failing tests for the extractor schema: a line carrying a net amount, a VAT rate and a gross amount records all three; a line printing one figure records one and leaves the tax fields null; a stated discount is recorded rather than netted into the total.
- [x] 2.2 Add `subtotal`, `tax_rate`, `tax_amount`, `discount` to `LineItem` in `ai_api/documents/extractor.py`, all optional, with field descriptions carrying the guidance (the reference implementation's approach — the schema instructs, the prompt stays short).
- [x] 2.3 Write failing tests for `ExtractedLines`: the document's own `total`, `tax` and `subtotal` are carried; a document with no totals block records null, distinguishable from a stated zero.
- [x] 2.4 Add those three fields to `ExtractedLines` and read them in the text path. Amounts come back as strings through `parse_amount`, like every other figure — no separator interpretation in the model.
- [x] 2.5 Carry the new fields through the **vision** path: add them to `VisionPage`, and merge totals from the **last** page stating one (as `total` already is) with per-line fields concatenating with their lines. Test that a two-page scan whose totals are on page 2 carries them.
- [x] 2.6 Test the merge asymmetry explicitly: a text-path and a vision-path reading of the same figures produce the same `ExtractedLines`. This is the change's easiest silent failure — scanned invoices reconciling worse than text ones, with no visible symptom.

## 3. Charges become lines

- [x] 3.1 Write failing tests: a document stating "shipping cost incl. VAT EUR 15.90" outside its line table yields a line for it; that line counts toward the reconciliation sum; a total-level *discount* does not become a line.
- [x] 3.2 Extend the extractor prompt and schema so totals-block charges are emitted as ordinary line items. Nothing marks them as special — a charge line must be indistinguishable downstream, because whether money went on a product or on delivering it is a categorization question.
- [x] 3.3 Test that a charge line is categorized by the next run like any other line, and that a human may correct and delete it.

## 4. Split the reconciliation rule

- [x] 4.1 Write failing tests in `apps/web-api/tests/` for the split rule in `web_api/reconcile.py`: lines matching the document's own total reconcile; lines missing one against the document's total do not; a document total differing from the posted total is a *disagreement*, not a reconciliation failure; a document with no total falls back to the existing gross-or-net comparison unchanged.
- [x] 4.2 Implement the split in `web_api/reconcile.py`, keeping the existing comparison intact as the no-document-total path. Both the stage and `InvoiceDetailRead.lines_reconciled` read it, so they cannot drift.
- [x] 4.3 Add a separate tolerance for the internal check, tighter than the cross-source one, configurable and both relative and absolute. Leave the value provisional and note that step 6 sets it.
- [x] 4.4 Pin the Aquatuning case as a regression test with its real figures — lines 36.64 + 31.41 + 20.90, shipping 15.90, document total 104.85, posted total 83.88, posted tax 0.00 — asserting acceptance. Verify it fails against the pre-split rule.

## 5. Store, surface, and stop rejecting

- [x] 5.1 Add `Invoice.document_total` / `document_tax` and `InvoiceLine.subtotal` / `tax_rate` / `tax_amount` / `discount` with one Alembic migration. All nullable, no backfill.
- [x] 5.2 Test that extraction writes the document's figures and **never** rewrites the posted `total`/`tax` — the rule `document_invoice_number` already follows.
- [x] 5.3 Change `process_invoice` to accept-and-flag on a cross-source mismatch: the lines are written, both totals stored, and the disagreement recorded. Reject only on the internal check.
- [x] 5.4 Add `totals_agree` to `InvoiceRead`, computed on read against the current tolerance. **Null, not true**, when the document stated no total — test that a client can distinguish "nothing to compare" from "compared and agreed".
- [x] 5.5 Test that widening the tolerance moves an existing invoice's verdict without rewriting a row.
- [x] 5.6 Show both totals in the voucher panel when they disagree, each labelled by source, and only the posted total when they agree or the document stated none. Test all three states, and that a `viewer` sees the same evidence.

## 6. Measure, and report what is left

- [ ] 6.1 **BLOCKED — vLLM on :8999 unreachable.** Re-run the six `failed` invoices through `POST /invoices/{id}/reprocess` and record the outcome per invoice against `baseline.md`.
- [~] 6.2 **PARTIAL — the deterministic half ran (no stored verdict moved, `results.md`); re-extraction needs vLLM.** Dry-run the 21 `processed` invoices and confirm none regresses — a stricter internal check could reject a document that the looser cross-source rule happened to accept. Any regression is a finding, not a rounding error.
- [~] 6.3 **PROVISIONAL — sized from five real documents, not a distribution; see `results.md`.** Set the internal tolerance from the measured distribution, replacing the provisional value from 4.3.
- [x] 6.4 Write `results.md`: before and after per invoice, what the remaining failures are, and which of them share a cause. Name the 2× double-count explicitly as out of scope and still open.
- [x] 6.5 Update `CLAUDE.md` — the document-processing section's reconciliation rule, the new invoice and line columns, charges as lines, and the new tolerance setting. Add the new env var to `.env.example`.
- [x] 6.6 Full suite green: `uv run pytest`, `./node_modules/.bin/tsc --noEmit`, frontend vitest, eslint at or below its current 52-problem baseline.
