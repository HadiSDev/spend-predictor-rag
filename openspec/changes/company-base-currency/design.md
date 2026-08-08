## Context

Money enters the system in whatever currency the ERP posted it in. `Invoice`,
`InvoiceLine` and `ErpEntry` each carry a nullable `currency` plus
`Numeric(14,2)` amounts, and `web_api/reporting.py` deliberately groups every
aggregate by `currency` so amounts of different currencies are never summed.
That rule is correct as a guard, but it is the reason a customer never sees one
total: a company buying in DKK, EUR and USD gets three rows where it wants one.

Constraints shaping the design:

- **Dependency direction is one-way.** `ai_api` imports the domain from
  `web_api`; `web_api` must never import `ai_api`. The conversion service is
  domain-level and therefore lives in `web_api`, where both the sync runner
  (`ai_api/sync/runner.py`) and the API can use it.
- **`web_api` makes no outbound HTTP today.** Clerk outbound calls exist but are
  disabled off-prod by default (`WEB_API_CLERK_OUTBOUND_DISABLED`). A rate
  provider is a second network dependency and must follow the same "off by
  default, fails soft" posture.
- **Re-sync is idempotent.** `_persist_invoices` / `_persist_entries` upsert on
  deterministic ids and re-run over the same rows; conversion must be safe to
  re-execute and must not thrash rows on every run.
- **The as-posted figure is evidence.** The user was explicit: the original
  currency and value stay, untouched, next to the converted one.

## Goals / Non-Goals

**Goals:**

- One currency per company, chosen by the customer, that every figure in the
  product can be presented in.
- Conversion at the rate that applied on the transaction's own date, with the
  rate and the effective rate date stored next to the result so any figure can
  be re-derived and defended.
- The original currency and amount preserved and reachable in the UI.
- Aggregates that sum into a single number in SQL, without per-row conversion at
  query time.
- Graceful degradation: no rate, no date, or no network means *unconverted*,
  never *wrongly converted*, and never a failed sync.

**Non-Goals:**

- Intraday, bid/ask, or contract-specific rates. ECB daily reference rates only.
- Per-user or per-organization display currency. The base currency is a company
  setting.
- Re-expressing the PDF `InvoiceFlow` ledger CSV, categorization inputs, or the
  ground-truth store in base currency — conversion is a presentation and
  aggregation concern, not a categorization one.
- Automatic re-conversion when a company changes its base currency. That is an
  explicit, operator-triggered recompute (see Decisions).
- Currency-aware VAT logic. `with_vat` semantics are untouched.

## Decisions

### 1. Base currency is a required `Company` column, not an org setting

`Company.base_currency: str` (ISO 4217, `String(3)`, non-null). A company is the
tenant that owns financial data and already carries `country_code`; an
organization may hold several companies in different countries, and forcing them
onto one currency would be exactly the flattening this change is trying to
avoid.

`POST /companies` requires it — the same reasoning as the required `integration`
block: a company whose figures cannot be presented is not a usable company.
Existing rows are backfilled by migration (most frequent `Invoice.currency` for
that company, else most frequent `ErpEntry.currency`, else `EUR`).

*Alternative rejected:* derive it from `country_code`. Wrong for a Danish
subsidiary that reports in EUR, and it makes an implicit choice the customer
never confirmed.

### 2. Rates cached against EUR; cross-rates derived

```
fx_rates(id, quote_currency, rate_date, published_date, rate, source, fetched_at)
  UNIQUE (quote_currency, rate_date)
```

`rate_date` is what you look a rate up by; `published_date` is the publication it
actually came from. They differ only on a non-publication date (see Decision 4),
and keeping both means a row cached under a Saturday can still report Friday as
its rate date rather than passing a lookup date off as a publication.

`rate` is EUR→quote (units of quote per 1 EUR), mirroring how the ECB publishes.
Any pair is derived: `rate(A→B) = rate(EUR→B) / rate(EUR→A)`, with
`rate(EUR→EUR) = 1`. Storing pairs instead would need O(n²) rows and n² fetches
for the same information.

`rate` is `Numeric(18,8)` — enough for JPY-scale and for the divisions above
without visible drift.

*Alternative rejected:* cache per (base, quote) pair as returned by the
provider. Simpler lookup, but the cache stops being reusable the moment a second
company picks a different base currency.

### 3. Frankfurter (ECB) behind a narrow provider seam

`src/web_api/fx/provider.py` defines a small `RateProvider` protocol
(`fetch(rate_date) -> dict[str, Decimal] | None`, EUR-based, one call per date)
with `FrankfurterProvider` as the only implementation. It is key-less, free,
ECB-backed, and returns the actual publication date it served — which is what
makes weekend/holiday handling honest rather than guessed.

The protocol exists so tests inject a `StubProvider` and never touch the
network; it is not an invitation to build a provider registry now.

Config: `FX_ENABLED` (default `false`; `true` in prod/dev with network),
`FX_PROVIDER_URL` (default `https://api.frankfurter.dev/v1`),
`FX_HTTP_TIMEOUT_SECONDS` (default `10`). `httpx` is added as a `web_api`
dependency.

### 4. Non-publication dates resolve backwards, and the resolved date is stored

The ECB publishes on TARGET business days only, so a Saturday invoice has no
rate of its own. The service asks the provider for the requested date and takes
the publication date the provider actually served (Frankfurter answers a
non-publication date with the prior publication day). That resolved date is
written to `fx_rate_date` on the row and cached under **both** dates, so the
Saturday lookup is a cache hit next time.

Forward-filling (using the *next* publication) is not used: it would mean
valuing a transaction at a rate that did not yet exist.

### 5. Conversion is materialized at write time, originals untouched

New columns (all nullable — null means "not converted"):

| Table | Columns |
|---|---|
| `invoices` | `base_currency`, `base_total`, `base_tax`, `fx_rate`, `fx_rate_date` |
| `invoice_lines` | `base_currency`, `base_amount`, `fx_rate`, `fx_rate_date` |
| `erp_entries` | `base_currency`, `base_debit_amount`, `base_credit_amount`, `fx_rate`, `fx_rate_date` |

`fx_rate` is `Numeric(18,8)` and reads **units of base per 1 unit of the posted
currency**, so `base_amount = amount × fx_rate` with no direction ambiguity.
Base amounts are `Numeric(14,2)`, quantized `ROUND_HALF_UP`, matching the
existing money columns.

Each amount is converted independently from its own source amount (never derived
from another base amount), so a `base_debit_amount` and `base_credit_amount` on
the same row are each a direct conversion.

Same-currency rows still get `base_currency`, `fx_rate = 1` and
`fx_rate_date = <transaction date>`, so "converted" and "not converted" is one
null check rather than a currency comparison.

*Alternative rejected:* convert at read time in reporting SQL. It leaves the
schema untouched and lets a corrected rate retroactively fix history, but every
report pays a join per row, exported figures are not reproducible, and a
customer's totals can change between two page loads with no record of why.

### 6. The purchase date is the row's own date, and a missing date blocks conversion

- `Invoice` → `invoice_date`
- `InvoiceLine` → its invoice's `invoice_date` (a line has no date of its own)
- `ErpEntry` → `accounting_date`

If that date is null, or the currency is null/unknown to the provider, or the
provider is disabled/unreachable, the row is persisted with base fields left
null. There is no fallback to today's rate and no fallback to `created_at`:
both would produce a number that looks authoritative and is not.

### 7. The runner converts during persist, and rate failures are isolated

`_persist_invoices` and `_persist_entries` call the conversion service as they
write. Conversion is skipped when the row already has a `fx_rate` and its
`base_currency` matches the company's — so re-syncs do not re-fetch or churn.

A rate-provider failure is recorded on that integration's `SyncState` the same
way an ERP failure is, but with a crucial difference: **an FX failure does not
fail the integration's sync.** Rows land unconverted and a later recompute fills
them in. Losing the ledger data because a public rate API was down would be a
worse outcome than a temporarily unconverted figure.

Rates are memoized per run in a process-local dict keyed by `(currency, date)`
on top of the DB cache, so a 5,000-entry sync spanning 90 days makes at most ~90
provider calls.

### 8. Reports gain `currency_mode`, defaulting to `base`

Every `/reports/*` endpoint — and `GET /erp-entries/vouchers`, whose group
totals are also sums — accepts `currency_mode=base|original` (default `base`).
The flat `/erp-entries` list and the entry/invoice detail endpoints need no mode:
they return rows, not sums, so they simply carry both figures.

- **`base`**: group by `base_currency` and sum the `base_*` columns. A dimension
  yields one row, in the customer's currency.
- **`original`**: today's exact behaviour, byte-for-byte — group by `currency`,
  sum the posted amounts.

In `base` mode, rows with a null base amount are excluded from the sum and
counted in a per-row `unconverted_count` (plus their posted total is *not*
folded in). Silently dropping them would understate spend; the count makes the
gap visible and actionable in the UI.

The existing "never sum across currencies" requirement is preserved, not
weakened: in `base` mode everything summed is already in one currency, and
`base_currency` is still a `GROUP BY` key, so a company mid-recompute produces
two visible rows rather than one wrong one.

### 9. Base-currency changes are recomputed explicitly

`PATCH /companies/{id}` accepts `base_currency` (management-gated, like other
company fields). It does **not** rewrite historical rows inline — that is an
unbounded write inside a request.

Two recompute paths, sharing one function:

- `POST /api/v1/companies/{id}/recompute-fx` (management) — recomputes that
  company's rows in batches, returns counts (`converted`, `unconverted`,
  `unchanged`).
- `python -m web_api.fx.backfill [--company-id …]` — the ops path, for bulk
  reruns after a rate correction or a provider change.

Between the PATCH and the recompute, that company's rows hold two different
`base_currency` values. Because reports group by `base_currency`, this shows up
as two rows — visibly stale, not silently wrong. The frontend prompts to
recompute immediately after a base-currency change.

### 10. UI shows base currency, original on hover

`formatMoney` already takes an explicit currency, so display-side changes are
localized. Entry/invoice tables render the base amount with the company's
currency; a tooltip on any converted cell shows the as-posted amount and
currency, the rate, and the rate date. The entry drawer shows the same as a
labelled block. A row with no base amount renders the original amount in its own
currency, visibly marked as unconverted.

Voucher grouping benefits directly: `_shared([e.currency …])` today yields null
whenever a voucher's postings disagree, so a mixed-currency voucher shows no
currency at all. In base mode the group's currency is the company's, and the
group total becomes meaningful.

## Risks / Trade-offs

- **[Public rate API becomes unavailable or changes shape]** → The provider seam
  is one file and one method; the DB cache means historical rates already
  fetched keep working offline. `FX_ENABLED=false` degrades the product to
  today's behaviour rather than breaking it.
- **[ECB does not publish every currency]** → Rows in an unsupported currency
  stay unconverted and are counted in `unconverted_count`. They are visible in
  reports rather than silently missing. A manual-rate table is the follow-up if
  a customer needs one.
- **[Stored base amounts drift from a corrected rate]** → Accepted, by design:
  the stored rate is the evidence of what was used. The recompute endpoint and
  CLI are the correction path.
- **[Mixed `base_currency` state after a base-currency change]** → Reports show
  it as separate rows and the UI prompts for recompute. Not hidden.
- **[Rounding: sum of converted lines ≠ converted invoice total]** → Real and
  unavoidable when each amount is converted independently. Accepted: each figure
  is individually correct and reproducible from its stored rate. Reconciliation
  views must not assert line-sum equality on base amounts.
- **[Backfill of `base_currency` guesses wrong for an existing company]** → The
  guess is a most-frequent-posted-currency heuristic and is trivially corrected
  in Settings followed by a recompute. It is applied only to rows that exist
  before this change ships.
- **[Sync slows down on first run over a wide date range]** → Bounded by the
  per-run memo plus the DB cache: one provider call per distinct date, ever.
- **[Schema growth on the three highest-volume tables]** → Five, four and five
  nullable columns respectively. Accepted in exchange for aggregation staying
  pure SQL `GROUP BY`.

## Migration Plan

1. **Ship schema first.** One Alembic revision: `fx_rates` table,
   `companies.base_currency` added nullable, base/rate columns added nullable on
   the three tables.
2. **Backfill `base_currency`** in the same revision (most-frequent posted
   currency per company, else `EUR`), then `ALTER … SET NOT NULL`.
3. **Deploy the backend** with `FX_ENABLED=false`. Nothing converts; every base
   column is null; `currency_mode=base` returns rows with a full
   `unconverted_count`, and `original` mode is unchanged. The product behaves
   exactly as before.
4. **Enable FX** (`FX_ENABLED=true`) and run `python -m web_api.fx.backfill` to
   populate the cache and the stored base amounts for existing data.
5. **Deploy the frontend** once step 4 reports a healthy converted ratio.
6. **Rollback**: set `FX_ENABLED=false` and point the frontend back to
   `currency_mode=original`. The added columns are nullable and unread in that
   mode, so no schema rollback is needed; the Alembic downgrade drops them only
   if the change is abandoned outright.

## Open Questions

- Should a company be allowed to have **no** base currency (opt out of
  conversion entirely)? Current design says no — required, defaulting sensibly —
  on the grounds that "one number" is the point of the feature.
- Which date does a **credit note or payment entry** belong to for FX purposes —
  its own `accounting_date` (current design) or the original invoice's date?
  Matching them would make a settlement net to zero in base currency; the
  current design shows the FX gain/loss instead, which is the accounting-correct
  view but may surprise a customer.
- Should `unconverted_count` surface as a dashboard-level data-quality warning,
  or stay a per-row field consumed only by tooltips?
