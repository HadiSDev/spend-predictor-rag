"""An invoice line names what was bought, beside describing it

Revision ID: 0006_line_item_name
Revises: 0005_invoice_corrections
Create Date: 2026-08-23

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0006_line_item_name'
down_revision = '0005_invoice_corrections'
branch_labels = None
depends_on = None


def _lines() -> sa.Table:
    """A typed handle on the two columns this migration touches."""
    return sa.table(
        'invoice_lines',
        sa.column('id', sa.String),
        sa.column('verified_fields', sa.JSON),
    )


def _move_verified(old: str, new: str) -> None:
    """Rewrite `old` to `new` in every line's `verified_fields`, in place."""
    lines = _lines()
    bind = op.get_bind()
    rows = bind.execute(sa.select(lines.c.id, lines.c.verified_fields)).fetchall()
    for row in rows:
        fields = row.verified_fields or []
        if old not in fields:
            continue
        moved = [new if f == old else f for f in fields]
        deduped = list(dict.fromkeys(moved))
        bind.execute(
            sa.update(lines).where(lines.c.id == row.id).values(verified_fields=deduped)
        )


def upgrade() -> None:
    op.add_column('invoice_lines', sa.Column('item_name', sa.String(), nullable=True))
    op.execute('UPDATE invoice_lines SET item_name = description')
    op.execute('UPDATE invoice_lines SET description = NULL')
    _move_verified('description', 'item_name')


def downgrade() -> None:
    _move_verified('item_name', 'description')
    op.execute('UPDATE invoice_lines SET description = item_name')
    op.drop_column('invoice_lines', 'item_name')
