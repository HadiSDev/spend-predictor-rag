"""Store what the document said about its own arithmetic.

Reconciliation asked whether *the document's lines* summed to *the ERP's total*
— two systems, two VAT conventions, one comparison — and rejected
correctly-read invoices for arithmetic that was never wrong. The document
usually states its own total; it was read past and discarded, so the only figure
available to compare against belonged to somebody else.

Seven columns, all nullable, no backfill. **Null means "no document said"**,
which is not a stated zero: a receipt frequently prints no totals block at all,
and folding the two together would make a document nobody could read look like
one that balances.

On `invoices`, the three figures sit **beside** `total`/`tax`, which extraction
still never rewrites — the rule `document_invoice_number` already establishes.
When the two disagree the disagreement *is* the information.

On `invoice_lines`, the four record what the document printed about that line's
tax. Gross-versus-net becomes read rather than inferred, and the inference is
what rejected an Aquatuning invoice whose line prices were VAT-inclusive and
whose posted total was net.

Revision ID: 0010_document_totals
Revises: 0009_categorization_cache
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_document_totals"
down_revision = "0009_categorization_cache"
branch_labels = None
depends_on = None

#: `(table, column, type)`. Money matches the columns it sits beside — a
#: document total is compared with `invoices.total`, so a wider or narrower
#: scale would introduce a rounding difference that is ours rather than the
#: document's. `tax_rate` is a percentage, not money.
_COLUMNS = (
    ("invoices", "document_total", sa.Numeric(14, 2)),
    ("invoices", "document_tax", sa.Numeric(14, 2)),
    ("invoices", "document_subtotal", sa.Numeric(14, 2)),
    ("invoice_lines", "subtotal", sa.Numeric(14, 2)),
    ("invoice_lines", "tax_amount", sa.Numeric(14, 2)),
    ("invoice_lines", "tax_rate", sa.Numeric(7, 3)),
    ("invoice_lines", "discount", sa.Numeric(14, 2)),
)


def upgrade() -> None:
    for table, column, type_ in _COLUMNS:
        op.add_column(table, sa.Column(column, type_, nullable=True))


def downgrade() -> None:
    for table, column, _ in reversed(_COLUMNS):
        op.drop_column(table, column)
