"""Append categorization results to the CSV ledger."""
from __future__ import annotations

import csv
from pathlib import Path

from .models import CategorizedInvoice, ExtractedInvoice, VerificationResult

LEDGER_COLUMNS = [
    "source_file",
    "status",
    "invoice_date",
    "vendor_name",
    "invoice_number",
    "total",
    "currency",
    "account_code",
    "account_name",
    "category",
    "arithmetic_ok",
    "confidence",
    "notes",
]


def build_ledger_row(
    *,
    source_file: str,
    skipped: bool,
    skip_reason: str,
    extracted: ExtractedInvoice | None,
    verification: VerificationResult | None,
    categorized: CategorizedInvoice | None,
    categorization_note: str = "",
    errored: bool = False,
    error_reason: str = "",
) -> dict:
    """Build a ledger row dict from flow results."""
    if skipped:
        row = {col: "" for col in LEDGER_COLUMNS}
        row["source_file"] = source_file
        row["status"] = "skipped"
        row["notes"] = skip_reason
        return row

    if errored:
        row = {col: "" for col in LEDGER_COLUMNS}
        row["source_file"] = source_file
        row["status"] = "error"
        row["notes"] = error_reason
        return row

    note_parts: list[str] = []
    if verification and verification.discrepancies:
        note_parts.append("; ".join(verification.discrepancies))
    elif verification and verification.notes:
        note_parts.append(verification.notes)
    if categorization_note:
        note_parts.append(categorization_note)
    notes = " | ".join(note_parts)

    return {
        "source_file": source_file,
        "status": "processed",
        "invoice_date": (extracted.invoice_date if extracted else "") or "",
        "vendor_name": extracted.vendor_name if extracted else "",
        "invoice_number": (extracted.invoice_number if extracted else "") or "",
        "total": extracted.total if extracted else "",
        "currency": (extracted.currency if extracted else "") or "",
        "account_code": categorized.account_code if categorized else "",
        "account_name": categorized.account_name if categorized else "",
        "category": categorized.category if categorized else "",
        "arithmetic_ok": verification.arithmetic_ok if verification else "",
        "confidence": categorized.confidence if categorized else "",
        "notes": notes,
    }


def append_row(row: dict, path: str | Path) -> None:
    """Append a row to the ledger CSV, writing the header if the file is new."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in LEDGER_COLUMNS})
