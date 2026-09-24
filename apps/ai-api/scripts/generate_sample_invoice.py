"""Generate a deterministic sample invoice PDF under data/invoices/."""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / "data" / "invoices" / "sample_invoice.pdf"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=letter)
    lines = [
        "INVOICE",
        "Vendor: Nimbus Cloud Services Inc.",
        "Invoice Number: INV-2026-0042",
        "Invoice Date: 2026-05-15",
        "Currency: USD",
        "",
        "Description                    Qty   Unit Price     Amount",
        "Managed Kubernetes hosting      1     1200.00       1200.00",
        "Object storage (1TB)            1      80.00          80.00",
        "",
        "Subtotal:   1280.00",
        "Tax (10%):   128.00",
        "Total:      1408.00",
    ]
    y = 740
    for line in lines:
        c.drawString(72, y, line)
        y -= 18
    c.showPage()
    c.save()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
