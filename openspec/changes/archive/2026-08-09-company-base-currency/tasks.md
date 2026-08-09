## 1. Domain model & migration

- [x] 1.1 Add `base_currency: str` (non-null, `String(3)`) to `Company` in `src/web_api/db/models/company.py`
- [x] 1.2 Add `FxRate` model in `src/web_api/db/models/fx_rate.py` (`quote_currency`, `rate_date`, `rate` `Numeric(18,8)`, `source`, `fetched_at`) with a unique constraint on `(quote_currency, rate_date)`, and export it from `db/models/__init__.py`
- [x] 1.3 Add `base_currency`, `base_total`, `base_tax`, `fx_rate` (`Numeric(18,8)`), `fx_rate_date` to `Invoice`
- [x] 1.4 Add `base_currency`, `base_amount`, `fx_rate`, `fx_rate_date` to `InvoiceLine`
- [x] 1.5 Add `base_currency`, `base_debit_amount`, `base_credit_amount`, `fx_rate`, `fx_rate_date` to `ErpEntry`
- [x] 1.6 Write the Alembic revision: create `fx_rates`, add all columns nullable, backfill `companies.base_currency` (most frequent `Invoice.currency`, else most frequent `ErpEntry.currency`, else `EUR`), then set it NOT NULL
- [x] 1.7 Verify `uv run alembic upgrade head` and `downgrade -1` both run clean on a populated dev database

## 2. FX service

- [x] 2.1 Add `httpx` to the project dependencies and `FX_ENABLED` (default false), `FX_PROVIDER_URL` (default `https://api.frankfurter.dev/v1`), `FX_HTTP_TIMEOUT_SECONDS` (default 10) to `src/web_api/config.py` and `.env.example`
- [x] 2.2 Create `src/web_api/fx/provider.py`: a `RateProvider` protocol (`fetch(rate_date) -> tuple[date, dict[str, Decimal]] | None`, EUR-based, returning the publication date actually served) plus `FrankfurterProvider` and a disabled null provider
- [x] 2.3 Create `src/web_api/fx/service.py`: `get_rate(session, from_currency, to_currency, on_date)` reading `fx_rates` first, fetching once on a miss, caching the served rates under both the requested and the served date, deriving cross-rates as `rate(EUR→B)/rate(EUR→A)`, returning `(rate, resolved_date)` or `None`
- [x] 2.4 Add a per-process/per-run memo in front of the DB cache so one date is resolved at most once per run
- [x] 2.5 Add `convert(amount, rate)` quantizing to 2 decimals `ROUND_HALF_UP`, and `apply_conversion(session, row, base_currency, on_date)` writing `base_*`, `fx_rate`, `fx_rate_date` — including the same-currency case (rate 1) and the skip-if-already-converted rule
- [x] 2.6 Unit-test the service with a `StubProvider`: cross-rate derivation, weekend backward resolution, cache hit counts, same-currency rate 1, rounding, and the null-on-missing-rate paths — no network in any test

## 3. Conversion in the sync runner

- [x] 3.1 Load the company's `base_currency` once per integration in `run_sync()` and thread it into the persist helpers
- [x] 3.2 Convert `total`/`tax` in `_persist_invoices` off `invoice_date`, and each line's `amount` off its invoice's `invoice_date`
- [x] 3.3 Convert `debit_amount`/`credit_amount` independently in `_persist_entries` off `accounting_date`
- [x] 3.4 Skip conversion for rows already carrying a rate whose `base_currency` matches the company's
- [x] 3.5 Catch every provider/rate failure inside persistence: log, leave base fields null, do not mark the integration failed, let the watermark advance
- [x] 3.6 Extend `tests/test_sync_runner.py`: converted rows, unconverted rows (no date, uncovered currency, provider down), idempotent re-sync, and one-lookup-per-date

## 4. Recompute & backfill

- [x] 4.1 Add `recompute_company(session, company_id)` in `src/web_api/fx/recompute.py` — batched over invoices, lines and entries, returning `(converted, unconverted, unchanged)` counts
- [x] 4.2 Add `python -m web_api.fx.backfill [--company-id …]` wrapping it for ops use
- [x] 4.3 Test recompute after a base-currency switch: base amounts rewritten at each row's own historical rate, posted amounts byte-identical

## 5. Web API — companies

- [x] 5.1 Add `base_currency` to `CompanyRead`; add it required (with ISO 4217 validation, uppercased) to `CompanyCreate` and optional to `CompanyUpdate` in `src/web_api/schemas.py`
- [x] 5.2 Thread `base_currency` through `POST /companies` (single transaction, unchanged) and `PATCH /companies/{id}` in `src/web_api/routers/companies.py`, without any inline rewrite of historical rows
- [x] 5.3 Add `POST /companies/{id}/recompute-fx` (management-gated, 404 out of scope) returning the recompute counts
- [x] 5.4 Extend `tests/web_api/test_management.py`: required-on-create, invalid code rejected, base currency returned on read, PATCH change, recompute authorization and counts

## 6. Web API — entries, invoices, reports

- [x] 6.1 Add the conversion fields to `ErpEntryRead` and populate them in `_entry_select()`/`_entry_read()` in `src/web_api/routers/erp_entries.py`
- [x] 6.2 Add `currency_mode=base|original` (default `base`) to `GET /erp-entries/vouchers`: totals summed from base amounts, group `currency` agreed on `base_currency`, plus `unconverted_count`; `original` preserves today's behaviour exactly
- [x] 6.3 Add the conversion fields to the invoice and invoice-line read schemas and their routers
- [x] 6.4 Add `currency_mode` to every `/reports/*` endpoint and implement base-mode aggregation in `src/web_api/reporting.py` — group by `base_currency`, sum `base_*`, count unconverted rows per group, reject an unknown mode with 422
- [x] 6.5 Extend `tests/web_api/test_erp_entries.py` and the reporting tests: both modes, mixed-currency voucher collapsing to one base total, `unconverted_count`, fully-unconverted dimension still returned, mid-recompute company yielding two rows

## 7. Frontend — settings

- [x] 7.1 Add an ISO 4217 currency list (code + name) and a searchable currency field built on the existing `Combobox`
- [x] 7.2 Add `base_currency` to the company create form (required, pre-selected from the chosen country) and the edit form in `frontend/src/components/settings/companies-panel.tsx`; show it in the company list
- [x] 7.3 Add the recompute prompt on base-currency change: confirm copy, `recompute-fx` call, in-flight state, result counts, error handling matching the other settings actions, and a way to trigger it later
- [x] 7.4 Add `base_currency` and the recompute call to `frontend/src/lib/companies.ts` and its types
- [x] 7.5 Extend `companies-panel.test.tsx`: required field, country pre-selection, read-only for viewers, recompute prompt and result

## 8. Frontend — entries & reports display

- [x] 8.1 Extend `frontend/src/lib/types.ts` + `entries.ts` + `reports.ts` with the conversion fields, `currency_mode`, and `unconverted_count`
- [x] 8.2 Request base mode from the entries and reports queries, resolving the active company's base currency for formatting
- [x] 8.3 Add a conversion disclosure (keyboard-reachable, not hover-only) on converted amounts showing posted amount + currency, rate, and rate date; suppress it for same-currency rows
- [x] 8.4 Show the full conversion as labelled fields in `entry-drawer.tsx`
- [x] 8.5 Mark unconverted amounts in their posted currency, and indicate when a group total excludes unconverted postings — never render unconverted money as `0.00`
- [x] 8.6 Extend the entries panel/voucher table tests: mixed-currency voucher shows one base total, unconverted marking, disclosure content, no cross-company currency merging

## 9. Verification

- [x] 9.1 `uv run pytest` green; confirm no test performs an outbound rate request
- [x] 9.2 `./node_modules/.bin/vitest run` (frontend) green
- [x] 9.3 End-to-end on dev data: migrated, enabled FX, ran the backfill (1182 rows converted, 0 unconverted, 66 provider calls); verified reproducibility, weekend back-resolution, and base-mode reports. UI pass still to be done against a running dev server
- [x] 9.4 Update `CLAUDE.md` — company base currency, the FX module and its env vars, `currency_mode` on reports/vouchers, and the recompute/backfill paths
