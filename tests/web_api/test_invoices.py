"""Invoice management tests."""
from __future__ import annotations

from .conftest import auth


def test_invoice_read_exposes_erp_provenance_by_default(client, seed):
    res = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA"))
    assert res.status_code == 200
    # Sync-created invoices are ERP evidence: their header is not correctable.
    assert res.json()["source"] == "erp"
