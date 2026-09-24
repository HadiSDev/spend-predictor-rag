"""Record where every invoice's document stands, before and after a change.

Writes nothing. It exists so a claim like "this change fixed four of the six
failures" is a measurement against a file rather than a recollection.

Two halves, because they cost very different amounts:

* the **ledger half** — posted total, posted tax, the lines currently stored and
  what they sum to — comes straight from the database and always runs;
* the **extraction half** — what the model reads off the document *now* — needs
  the deployment and the ERP, and is only attempted with ``--extract``.

The failures carry their own arithmetic already: `doc_error` records the sum the
extraction produced and the totals it was judged against, so the six rejected
invoices are measurable without re-reading a single document.
"""
from __future__ import annotations

import argparse
from decimal import Decimal

from sqlmodel import Session, select

from web_api.db.models import Invoice, InvoiceLine
from web_api.db.session import engine

_ZERO = Decimal("0")


def _rows(session: Session) -> list[dict]:
    invoices = list(session.exec(select(Invoice).order_by(Invoice.invoice_date, Invoice.id)).all())
    out = []
    for inv in invoices:
        lines = list(
            session.exec(
                select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)
            ).all()
        )
        total = sum((l.amount for l in lines if l.amount is not None), _ZERO)
        out.append(
            {
                "id": inv.id,
                "number": inv.document_invoice_number or inv.invoice_number,
                "supplier": inv.supplier_name,
                "doc_status": getattr(inv.doc_status, "value", inv.doc_status),
                "currency": inv.currency,
                "total": inv.total,
                "tax": inv.tax,
                "n_lines": len(lines),
                "lines_sum": total,
                "origins": sorted({getattr(l.origin, "value", l.origin) for l in lines}),
                "error": (inv.doc_error or "").strip(),
            }
        )
    return out


def _table(rows: list[dict]) -> str:
    head = (
        "| invoice | supplier | doc_status | cur | posted total | posted tax | "
        "lines | lines sum | origin |\n"
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |\n"
    )
    body = "".join(
        "| {number} | {supplier} | {doc_status} | {currency} | {total} | {tax} | "
        "{n_lines} | {lines_sum} | {origin} |\n".format(
            **r, origin=", ".join(r["origins"]) or "—"
        )
        for r in rows
    )
    return head + body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help="Write the report here instead of stdout")
    args = parser.parse_args(argv)

    with Session(engine) as session:
        rows = _rows(session)

    failed = [r for r in rows if r["doc_status"] == "failed"]
    report = [
        "# Document baseline\n",
        f"\n{len(rows)} invoices: "
        + ", ".join(
            f"{n} {s}"
            for s, n in sorted(
                {r["doc_status"]: sum(1 for x in rows if x["doc_status"] == r["doc_status"]) for r in rows}.items()
            )
        )
        + "\n\n",
        _table(rows),
        "\n## The failures, with the reason each recorded\n\n",
    ]
    for r in failed:
        report.append(f"- **{r['number']}** ({r['supplier']}) — {r['error'] or 'no reason recorded'}\n")

    text = "".join(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
