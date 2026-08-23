"""`line_ground_truth` is cleaned up by the database, not by `web_api`.

`web_api.company_deletion` destroys a company's invoice lines and relies on this
table's rows going with them. It cannot do that itself: the table belongs to
`ai_api`, and the dependency runs one way — `ai_api` imports the domain from
`web_api`, never the reverse. So the foreign key's `ON DELETE CASCADE` is the
only mechanism available, and it is the one such cascade in the whole schema.

Asserted as a declaration rather than exercised as behaviour, deliberately. Both
test suites run on SQLite, which does not enforce foreign keys at all unless
`PRAGMA foreign_keys=ON` is set — so a runtime test would pass on a dropped
cascade and fail to warn anyone. What this pins is the thing that would actually
change: someone removing `ondelete` and quietly breaking a purge that only runs
on PostgreSQL.
"""
from __future__ import annotations

from ai_api.persistence.ground_truth import LineGroundTruth


def test_the_line_reference_cascades_on_delete():
    (fk,) = list(LineGroundTruth.__table__.c.invoice_line_id.foreign_keys)

    assert fk.column.table.name == "invoice_lines"
    assert fk.ondelete == "CASCADE", (
        "web_api.company_deletion depends on this: it deletes invoice lines and "
        "cannot reach ai_api's table to clean up after them"
    )
