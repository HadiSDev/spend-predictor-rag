"""`line_ground_truth` is cleaned up by the database, not by `web_api`."""
from __future__ import annotations

from ai_api.persistence.ground_truth import LineGroundTruth


def test_the_line_reference_cascades_on_delete():
    (fk,) = list(LineGroundTruth.__table__.c.invoice_line_id.foreign_keys)

    assert fk.column.table.name == "invoice_lines"
    assert fk.ondelete == "CASCADE", (
        "web_api.company_deletion depends on this: it deletes invoice lines and "
        "cannot reach ai_api's table to clean up after them"
    )
