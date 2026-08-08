"""Company base currency + FX rate cache + per-row conversion columns

Revision ID: 0016_base_currency
Revises: 0015_erp_entry_cleanup
Create Date: 2026-08-08

Adds the base-currency concept:

* ``fx_rates`` — daily reference rates, units of ``quote_currency`` per 1 EUR,
  unique on ``(quote_currency, rate_date)``. Reference data: no tenant columns.
* ``companies.base_currency`` — added nullable, backfilled from the currency
  each company's data is most often posted in (invoices first, then entries,
  else EUR), then set NOT NULL.
* Conversion columns on ``invoices``, ``invoice_lines`` and ``erp_entries``,
  all nullable — null means "not converted", never "converted to zero". The
  as-posted currency and amount columns are untouched.

Reversible: downgrade drops the added columns and the table. The backfilled
base currencies are not reconstructed on a re-upgrade, but the same heuristic
would produce the same values.

Note: the revision id is kept <=32 chars to fit ``alembic_version.version_num``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0016_base_currency"
down_revision = "0015_erp_entry_cleanup"
branch_labels = None
depends_on = None


# Most frequent non-null currency per company, invoices preferred over entries.
# A company with no posted amounts at all falls back to EUR.
_BACKFILL = """
WITH counts AS (
    SELECT company_id, currency, COUNT(*) AS n, 0 AS pref
    FROM invoices WHERE currency IS NOT NULL
    GROUP BY company_id, currency
    UNION ALL
    SELECT company_id, currency, COUNT(*) AS n, 1 AS pref
    FROM erp_entries WHERE currency IS NOT NULL
    GROUP BY company_id, currency
),
ranked AS (
    SELECT company_id, currency,
           ROW_NUMBER() OVER (
               PARTITION BY company_id ORDER BY pref, n DESC, currency
           ) AS rn
    FROM counts
)
UPDATE companies SET base_currency = ranked.currency
FROM ranked
WHERE ranked.company_id = companies.id AND ranked.rn = 1
"""


def upgrade() -> None:
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("published_date", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_currency", "rate_date", name="uq_fx_rate_ccy_date"),
    )
    op.create_index("ix_fx_rates_quote_currency", "fx_rates", ["quote_currency"])
    op.create_index("ix_fx_rates_rate_date", "fx_rates", ["rate_date"])

    op.add_column("companies", sa.Column("base_currency", sa.String(length=3), nullable=True))
    op.execute(_BACKFILL)
    op.execute("UPDATE companies SET base_currency = 'EUR' WHERE base_currency IS NULL")
    op.alter_column("companies", "base_currency", nullable=False)

    op.add_column("invoices", sa.Column("base_currency", sa.String(length=3), nullable=True))
    op.add_column("invoices", sa.Column("base_total", sa.Numeric(14, 2), nullable=True))
    op.add_column("invoices", sa.Column("base_tax", sa.Numeric(14, 2), nullable=True))
    op.add_column("invoices", sa.Column("fx_rate", sa.Numeric(18, 8), nullable=True))
    op.add_column("invoices", sa.Column("fx_rate_date", sa.Date(), nullable=True))

    op.add_column("invoice_lines", sa.Column("base_currency", sa.String(length=3), nullable=True))
    op.add_column("invoice_lines", sa.Column("base_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("invoice_lines", sa.Column("fx_rate", sa.Numeric(18, 8), nullable=True))
    op.add_column("invoice_lines", sa.Column("fx_rate_date", sa.Date(), nullable=True))

    op.add_column("erp_entries", sa.Column("base_currency", sa.String(length=3), nullable=True))
    op.add_column("erp_entries", sa.Column("base_debit_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("erp_entries", sa.Column("base_credit_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("erp_entries", sa.Column("fx_rate", sa.Numeric(18, 8), nullable=True))
    op.add_column("erp_entries", sa.Column("fx_rate_date", sa.Date(), nullable=True))


def downgrade() -> None:
    for column in ("fx_rate_date", "fx_rate", "base_credit_amount",
                   "base_debit_amount", "base_currency"):
        op.drop_column("erp_entries", column)
    for column in ("fx_rate_date", "fx_rate", "base_amount", "base_currency"):
        op.drop_column("invoice_lines", column)
    for column in ("fx_rate_date", "fx_rate", "base_tax", "base_total", "base_currency"):
        op.drop_column("invoices", column)
    op.drop_column("companies", "base_currency")

    op.drop_index("ix_fx_rates_rate_date", table_name="fx_rates")
    op.drop_index("ix_fx_rates_quote_currency", table_name="fx_rates")
    op.drop_table("fx_rates")
