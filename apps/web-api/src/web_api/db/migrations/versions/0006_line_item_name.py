"""An invoice line names what was bought, beside describing it

Revision ID: 0006_line_item_name
Revises: 0005_invoice_corrections
Create Date: 2026-08-23

``invoice_lines.item_name`` — the product or service as its source named it.
Short, expected on every line, and the value a supplier comparison is actually
about: "Figma Organization seat" is comparable across suppliers in a way that a
sentence of prose is not.

Unlike ``0003``, this one **does** backfill, because the value is already here.
Until now a line had exactly one free-text field and it was doing both jobs — an
extractor's description, an ERP bill line's text and a posting's memo all landed
in ``description``, and in every case what they actually hold is the *name*. So
the column is moved rather than added beside an empty one:

    item_name := description ;  description := NULL

Nullable despite being the always-present field: a stand-in line is built from a
ledger memo that is itself frequently null, and NOT NULL would force the sync to
invent a name.

**``verified_fields`` moves with the value.** A line whose ``verified_fields``
holds ``"description"`` carries a human's assertion about a value that is about
to live in a different column. Left alone, the sync's guard would protect an
now-empty ``description`` while freely overwriting the ``item_name`` that holds
the human's actual work — the guarantee exactly inverted, by a migration. So the
same upgrade rewrites the entry. It is done row-by-row in Python rather than in
SQL because the column is portable JSON and there is no one JSON-mutation
dialect that runs on both PostgreSQL and the SQLite suite.

Reversible: the downgrade copies the values back and reverses the rewrite. It is
not, however, recoverable from the audit log — this is a schema move, not a
correction, and no ``AuditLog`` row is written. Take a backup first.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# Kept under 32 characters: `alembic_version.version_num` is varchar(32), so a
# longer id fails the upgrade at the very last statement, after all its DDL has
# run. tests/web_api/test_migrations.py is what catches that.
revision = '0006_line_item_name'
down_revision = '0005_invoice_corrections'
branch_labels = None
depends_on = None


def _lines() -> sa.Table:
    """A typed handle on the two columns this migration touches.

    Declared with `sa.JSON` so SQLAlchemy serializes on the way in and
    deserializes on the way out for *both* backends — a raw `text()` query
    returns a decoded list on PostgreSQL and a JSON string on SQLite, and code
    that has to guess which is code that breaks on one of them.
    """
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
        # Order is preserved and duplicates are avoided: a row that somehow
        # already names the target keeps one entry, not two.
        moved = [new if f == old else f for f in fields]
        deduped = list(dict.fromkeys(moved))
        bind.execute(
            sa.update(lines).where(lines.c.id == row.id).values(verified_fields=deduped)
        )


def upgrade() -> None:
    op.add_column('invoice_lines', sa.Column('item_name', sa.String(), nullable=True))
    # The move, in two statements rather than one: every line's text becomes its
    # name, and nothing is left behind in the column that no longer means it.
    op.execute('UPDATE invoice_lines SET item_name = description')
    op.execute('UPDATE invoice_lines SET description = NULL')
    _move_verified('description', 'item_name')


def downgrade() -> None:
    _move_verified('item_name', 'description')
    op.execute('UPDATE invoice_lines SET description = item_name')
    op.drop_column('invoice_lines', 'item_name')
