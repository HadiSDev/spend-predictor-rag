"""Baseline schema — squash of the original 20 migrations

Revision ID: 0001_baseline_schema
Revises:
Create Date: 2026-08-09

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision = '0001_baseline_schema'
down_revision = None
branch_labels = None
depends_on = None

_AUDIT_SEQUENCE = "audit_log_seq_seq"
_AUDIT_SEQ_UNIQUE = "uq_audit_log_seq"

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
