## Why

Every monetary figure in the product is reported in the currency it was posted
in, so a Danish company with EUR, USD and SEK suppliers sees its spend split
across four incomparable buckets and never a single total. Customers think in
one currency — their own — and a spend-analytics product that cannot answer
"what did we spend last quarter?" in one number is not doing its job.

Conversion has to be done at the rate that applied **on the date of the
purchase**, not today's rate: restating a 2024 invoice at a 2026 rate silently
rewrites history and makes period-over-period comparisons meaningless. That
means the system needs historical daily rates, and it needs to keep the rate it
used as evidence next to the amount it produced.

## What Changes

- **Companies get a base currency.** `Company` gains a required
  `base_currency` (ISO 4217), set at creation and editable in Settings. It is
  the single currency the customer's figures are presented in.
- **Historical FX rates are fetched and cached.** A new `fx_rates` table caches
  daily ECB reference rates (via the free, key-less Frankfurter API), one row
  per `(quote_currency, rate_date)` against EUR; any cross-rate is derived from
  two cached rows. A rate is fetched at most once. Non-publication dates
  (weekends, TARGET holidays) resolve to the most recent prior publication, and
  the date actually used is recorded.
- **Converted amounts are persisted next to the originals.** `Invoice`,
  `InvoiceLine` and `ErpEntry` gain `base_currency`, base amount column(s),
  `fx_rate` and `fx_rate_date`. **The as-posted currency and amount columns are
  never overwritten** — they remain the evidence, and the stored rate makes
  every converted figure reproducible and auditable.
- **The sync runner converts as it persists.** Conversion happens once, at
  write time, keyed on the row's own purchase date (`Invoice.invoice_date`,
  `ErpEntry.accounting_date`; a line inherits its invoice's date). A row with no
  date, an unknown currency, or an unreachable rate provider is persisted
  **unconverted** rather than converted wrongly.
- **Reports aggregate in the base currency.** Reporting endpoints gain a
  `currency_mode=base|original` parameter (default `base`). In base mode a
  dimension yields one row in the company's currency instead of one row per
  posted currency; rows that could not be converted are counted, never silently
  dropped. `currency_mode=original` preserves today's exact behaviour.
- **Entry, voucher and invoice reads expose both.** Payloads carry the base
  amount plus the original amount, currency, rate and rate date.
- **The UI shows the base currency, with the original one hover away.** Tables,
  totals and reports render the company's currency; the original amount,
  currency, rate and rate date appear in tooltips and in the entry drawer.
- **Recompute path for corrections and base-currency changes.** A management
  endpoint and an ops CLI recompute stored base amounts for a company — needed
  when a customer switches base currency or a rate is corrected.
- **BREAKING**: `POST /api/v1/companies` requires `base_currency`. Existing
  company rows are backfilled by migration (most-frequent posted currency,
  falling back to `EUR`).

## Capabilities

### New Capabilities

- `currency-conversion`: the base-currency concept, historical rate sourcing and
  caching, the conversion rules (which date, which rate, what happens when a
  rate is unavailable), rounding, and the recompute/backfill path.

### Modified Capabilities

- `domain-model`: `Company.base_currency`; base-amount/rate columns on
  `Invoice`, `InvoiceLine` and `ErpEntry`; the new `FxRate` entity.
- `web-api-company-management`: `base_currency` on company create (required),
  update and read; the recompute-FX management action.
- `web-api-reporting`: `currency_mode` parameter, base-currency aggregation, and
  reporting of amounts that could not be converted.
- `web-api-entry-review`: entry, voucher-group and entry-detail payloads carry
  base amount, rate and rate date alongside the as-posted values.
- `web-api-invoice-review`: invoice and invoice-line payloads carry the same
  conversion fields.
- `sync-pipeline-orchestration`: the runner converts at persist time and
  isolates rate-provider failures the way it already isolates ERP failures.
- `frontend-settings`: base-currency selection in company settings, and the
  prompt to recompute after changing it.
- `frontend-erp-entries`: base-currency display with the original amount, rate
  and rate date surfaced on hover and in the drawer.

## Impact

- **New**: `src/web_api/fx/` (rate provider, cache, conversion service,
  backfill CLI); `fx_rates` table.
- **Schema**: Alembic migration adding `companies.base_currency`, base/rate
  columns on `invoices`, `invoice_lines`, `erp_entries`, and the `fx_rates`
  table, plus the backfill of existing companies.
- **Backend**: `web_api/db/models/{company,invoice,invoice_line,erp_entry}.py`,
  `web_api/schemas.py`, `web_api/routers/{companies,erp_entries,invoices,
  invoice_lines,reports}.py`, `web_api/reporting.py`, `web_api/integrations.py`
  (company creation path), `ai_api/sync/runner.py`.
- **Frontend**: `lib/format.ts`, `lib/{companies,entries,reports}.ts`,
  `components/settings/companies-panel.tsx`,
  `components/entries/{entries-panel,entry-table,voucher-table,entry-drawer}.tsx`,
  dashboard report cards.
- **Config/deps**: `FX_PROVIDER_URL`, `FX_ENABLED`, `FX_HTTP_TIMEOUT_SECONDS`
  in `.env.example`; an HTTP client (`httpx`) in `web_api`.
- **Outbound network**: first-ever outbound HTTP from `web_api` to a public
  rate API. It is off by default in tests and fails soft — no conversion rather
  than a failed sync.
- **Not affected**: the PDF `InvoiceFlow`/ledger CSV path, categorization, and
  the ground-truth store.
