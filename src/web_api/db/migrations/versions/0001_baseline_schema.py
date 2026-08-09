"""Baseline schema — squash of the original 20 migrations

Revision ID: 0001_baseline_schema
Revises:
Create Date: 2026-08-09

**This is a squash.** It replaces the original chain ``0001_add_clerk_external_ids``
… ``0020_erp_account_natural_key`` with a single migration that creates the whole
schema those twenty ended at. The old files are gone from this directory;
``0001``–``0019`` remain in git history — read them there if you need to know
*why* a column looks the way it does. ``0020_erp_account_natural_key`` was never
committed, so its source is preserved out of band at
``.superpowers/sdd/2026-08-08-voucher-detail-panel/migration-backup/`` (that
directory is gitignored) along with a copy of the whole original chain.

**Why the squash.** The original chain had no initial schema migration at all:
its base revision opened with ``ALTER TABLE organizations`` and not one of the
twenty contained a ``create_table`` for a base table. The schema was created
out-of-band by ``SQLModel.metadata.create_all()``, so ``alembic upgrade head``
against a fresh database failed immediately (``UndefinedTable: relation
"organizations" does not exist``), and running ``create_all`` first and *then*
upgrading failed just as fast on ``DuplicateColumn``. No one could stand up a
new database from the migrations. After this squash ``alembic upgrade head``
works from an empty database, which is the point.

**Existing databases must be stamped, not upgraded.** A database already at
``0020_erp_account_natural_key`` (the dev database, and any deployed one) already
*has* this schema — running ``upgrade`` there would try to create tables that
exist. Bring it across with::

    uv run alembic stamp 0001_baseline_schema

which only rewrites ``alembic_version``. Only a genuinely empty database should
ever run ``upgrade`` on this revision.

**Two things ``create_all``/autogenerate cannot express are hand-added below**,
and both are load-bearing:

1. ``audit_log.seq`` — the model declares ``server_default=FetchedValue()``,
   which deliberately renders *no* DDL (that is what makes the ORM omit ``seq``
   from its INSERTs so the database's own default applies). Autogenerate
   therefore emits a bare ``seq BIGINT NOT NULL`` with no default and no
   sequence, and every audit write fails with ``NotNullViolation`` — precisely
   the bug the original ``0019_audit_log_seq`` was written to fix. The real
   sequence, the column default and the unique constraint are created
   explicitly. (``0019``'s data backfill is deliberately *not* carried over: a
   freshly created table is empty.)
2. ``erp_accounts`` unique ``(erp_integration_id, erp_account_code)`` — added by
   the original ``0020``. The model now declares it too, so autogenerate emits
   it; it is asserted here anyway rather than left to depend on that.
   ``0020``'s duplicate-merge logic is not carried over — it was a one-time
   dedupe of rows a fresh database does not have.

**PostgreSQL only**, like the rest of this directory. ``env.py`` reads
``DATABASE_URL``, which is always a ``postgresql://`` URL in this project. The
test suite never runs migrations: it builds its schema with
``SQLModel.metadata.create_all()`` against in-memory SQLite, where
``db/models/audit_log.py`` supplies its own fallback for ``seq``. The dialect
assertion below fails loudly rather than half-succeeding somewhere else.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision = '0001_baseline_schema'
down_revision = None
branch_labels = None
depends_on = None

# audit_log.seq — see the module docstring. Names match the original
# 0019_audit_log_seq exactly, so a database stamped across from that migration
# and one built from this baseline are indistinguishable.
_AUDIT_SEQUENCE = "audit_log_seq_seq"
_AUDIT_SEQ_UNIQUE = "uq_audit_log_seq"

# erp_accounts natural key — name matches the original 0020, same reason.
_ERP_ACCOUNT_UNIQUE = "uq_erp_accounts_integration_code"


def _require_postgresql() -> None:
    dialect = op.get_bind().dialect.name
    if dialect != "postgresql":
        raise RuntimeError(
            f"0001_baseline_schema targets PostgreSQL only, got {dialect!r}. "
            "See the module docstring."
        )


def upgrade() -> None:
    _require_postgresql()

    op.create_table('audit_log',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('entity_type', sa.String(), nullable=False),
    sa.Column('entity_id', sa.String(), nullable=False),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('actor', sa.String(), nullable=False),
    sa.Column('changes', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    # No server_default here on purpose: the model's FetchedValue() renders no
    # DDL, so the real nextval() default is attached explicitly further down.
    sa.Column('seq', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('seq', name=_AUDIT_SEQ_UNIQUE)
    )
    op.create_index(op.f('ix_audit_log_entity_id'), 'audit_log', ['entity_id'], unique=False)
    op.create_table('fx_rates',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('quote_currency', sa.String(length=3), nullable=False),
    sa.Column('rate_date', sa.Date(), nullable=False),
    sa.Column('published_date', sa.Date(), nullable=False),
    sa.Column('rate', sa.Numeric(precision=18, scale=8), nullable=False),
    sa.Column('source', sa.String(), nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('quote_currency', 'rate_date', name='uq_fx_rate_ccy_date')
    )
    op.create_index(op.f('ix_fx_rates_quote_currency'), 'fx_rates', ['quote_currency'], unique=False)
    op.create_index(op.f('ix_fx_rates_rate_date'), 'fx_rates', ['rate_date'], unique=False)
    op.create_table('organizations',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('slug', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('suspended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('clerk_org_id', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('clerk_org_id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('vendors',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('country_code', sa.String(), nullable=True),
    sa.Column('vat_number', sa.String(), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('webhook_events',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('provider', sa.String(), nullable=False),
    sa.Column('event_id', sa.String(), nullable=False),
    sa.Column('event_type', sa.String(), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.Column('processed', sa.Boolean(), nullable=False),
    sa.Column('error', sa.String(), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id')
    )
    op.create_table('companies',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('organization_id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('country_code', sa.String(), nullable=True),
    sa.Column('vat_number', sa.String(), nullable=True),
    sa.Column('base_currency', sa.String(length=3), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('organization_id', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('is_system_admin', sa.Boolean(), nullable=False),
    sa.Column('clerk_user_id', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('clerk_user_id')
    )
    op.create_table('erp_integrations',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('company_id', sa.String(), nullable=False),
    sa.Column('erp_type', sa.String(), nullable=False),
    sa.Column('label', sa.String(), nullable=True),
    sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('disconnected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('files',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('company_id', sa.String(), nullable=False),
    sa.Column('uploaded_by', sa.String(), nullable=True),
    sa.Column('filename', sa.String(), nullable=False),
    sa.Column('file_type', sa.String(), nullable=False),
    sa.Column('storage_path', sa.String(), nullable=False),
    sa.Column('file_size', sa.Numeric(precision=12, scale=0), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('recommendations',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('company_id', sa.String(), nullable=False),
    sa.Column('rec_type', sa.String(), nullable=False),
    sa.Column('category_level_2', sa.String(), nullable=True),
    sa.Column('category_level_3', sa.String(), nullable=True),
    sa.Column('current_vendor_id', sa.String(), nullable=True),
    sa.Column('current_vendor_name', sa.String(), nullable=True),
    sa.Column('annual_spend', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('alternative_name', sa.String(), nullable=True),
    sa.Column('estimated_savings', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('savings_pct', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('confidence', sa.Numeric(precision=4, scale=3), nullable=True),
    sa.Column('source', sa.String(), nullable=True),
    sa.Column('rationale', sa.String(), nullable=True),
    sa.Column('dismissed', sa.Boolean(), nullable=False),
    sa.Column('gt_savings', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['current_vendor_id'], ['vendors.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('spend_categories',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('company_id', sa.String(), nullable=False),
    sa.Column('level_1', sa.String(), nullable=True),
    sa.Column('level_2', sa.String(), nullable=False),
    sa.Column('level_3', sa.String(), nullable=True),
    sa.Column('level_4', sa.String(), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('erp_accounts',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('erp_integration_id', sa.String(), nullable=False),
    sa.Column('erp_account_code', sa.String(), nullable=False),
    sa.Column('erp_account_name', sa.String(), nullable=False),
    sa.Column('erp_account_type', sa.String(), nullable=True),
    sa.Column('parent_code', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('sync_enabled', sa.Boolean(), nullable=False),
    sa.Column('with_vat', sa.Boolean(), nullable=False),
    sa.Column('raw_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['erp_integration_id'], ['erp_integrations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    # The natural key the original 0020 added. An ERP account is identified by
    # (integration, code); without this the chart of accounts can be stored twice.
    sa.UniqueConstraint('erp_integration_id', 'erp_account_code', name=_ERP_ACCOUNT_UNIQUE)
    )
    op.create_table('erp_credentials',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('erp_integration_id', sa.String(), nullable=False),
    sa.Column('encrypted_config', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['erp_integration_id'], ['erp_integrations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('erp_integration_id')
    )
    op.create_table('invoices',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('company_id', sa.String(), nullable=False),
    sa.Column('vendor_id', sa.String(), nullable=True),
    sa.Column('file_id', sa.String(), nullable=True),
    sa.Column('invoice_number', sa.String(), nullable=True),
    sa.Column('invoice_date', sa.Date(), nullable=True),
    sa.Column('currency', sa.String(), nullable=True),
    sa.Column('total', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('tax', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('base_currency', sa.String(length=3), nullable=True),
    sa.Column('base_total', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('base_tax', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('fx_rate', sa.Numeric(precision=18, scale=8), nullable=True),
    sa.Column('fx_rate_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('raw_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['file_id'], ['files.id'], ),
    sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sync_state',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('erp_integration_id', sa.String(), nullable=False),
    sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_invoice_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['erp_integration_id'], ['erp_integrations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('invoice_lines',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('company_id', sa.String(), nullable=False),
    sa.Column('invoice_id', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=12, scale=4), nullable=True),
    sa.Column('unit_price', sa.Numeric(precision=12, scale=4), nullable=True),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('native_account_code', sa.String(), nullable=True),
    sa.Column('base_currency', sa.String(length=3), nullable=True),
    sa.Column('base_amount', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('fx_rate', sa.Numeric(precision=18, scale=8), nullable=True),
    sa.Column('fx_rate_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('level_1', sa.String(), nullable=True),
    sa.Column('level_2', sa.String(), nullable=True),
    sa.Column('level_3', sa.String(), nullable=True),
    sa.Column('account_code', sa.String(), nullable=True),
    sa.Column('account_name', sa.String(), nullable=True),
    sa.Column('confidence', sa.Numeric(precision=4, scale=3), nullable=True),
    sa.Column('rationale', sa.String(), nullable=True),
    sa.Column('spend_category_id', sa.String(), nullable=True),
    sa.Column('raw_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ),
    sa.ForeignKeyConstraint(['spend_category_id'], ['spend_categories.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('erp_entries',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('company_id', sa.String(), nullable=False),
    sa.Column('erp_account_id', sa.String(), nullable=False),
    sa.Column('source_invoice_id', sa.String(), nullable=True),
    sa.Column('source_invoice_line_id', sa.String(), nullable=True),
    sa.Column('voucher_id', sa.String(), nullable=True),
    sa.Column('entry_type', sa.String(), nullable=False),
    sa.Column('accounting_date', sa.Date(), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('debit_amount', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('credit_amount', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('currency', sa.String(), nullable=True),
    sa.Column('erp_entry_id', sa.String(), nullable=True),
    sa.Column('base_currency', sa.String(length=3), nullable=True),
    sa.Column('base_debit_amount', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('base_credit_amount', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('fx_rate', sa.Numeric(precision=18, scale=8), nullable=True),
    sa.Column('fx_rate_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('raw_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['erp_account_id'], ['erp_accounts.id'], ),
    sa.ForeignKeyConstraint(['source_invoice_id'], ['invoices.id'], ),
    sa.ForeignKeyConstraint(['source_invoice_line_id'], ['invoice_lines.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # --- audit_log.seq: the part no autogenerate can produce ------------------
    # `OWNED BY` ties the sequence's lifetime to the column, so dropping the
    # table (or the column) drops the sequence with it. Nothing is backfilled:
    # the table was created empty a few statements ago.
    op.execute(f"CREATE SEQUENCE {_AUDIT_SEQUENCE} OWNED BY audit_log.seq")
    op.execute(
        f"ALTER TABLE audit_log ALTER COLUMN seq SET DEFAULT nextval('{_AUDIT_SEQUENCE}')"
    )


def downgrade() -> None:
    _require_postgresql()

    op.execute("ALTER TABLE audit_log ALTER COLUMN seq DROP DEFAULT")
    op.execute(f"DROP SEQUENCE IF EXISTS {_AUDIT_SEQUENCE}")

    op.drop_table('erp_entries')
    op.drop_table('invoice_lines')
    op.drop_table('sync_state')
    op.drop_table('invoices')
    op.drop_table('erp_credentials')
    op.drop_table('erp_accounts')
    op.drop_table('spend_categories')
    op.drop_table('recommendations')
    op.drop_table('files')
    op.drop_table('erp_integrations')
    op.drop_table('users')
    op.drop_table('companies')
    op.drop_table('webhook_events')
    op.drop_table('vendors')
    op.drop_index(op.f('ix_fx_rates_rate_date'), table_name='fx_rates')
    op.drop_index(op.f('ix_fx_rates_quote_currency'), table_name='fx_rates')
    op.drop_table('fx_rates')
    op.drop_table('organizations')
    op.drop_index(op.f('ix_audit_log_entity_id'), table_name='audit_log')
    op.drop_table('audit_log')
