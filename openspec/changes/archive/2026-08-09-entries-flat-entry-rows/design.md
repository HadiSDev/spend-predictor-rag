## Context

`/entries` renders `VoucherTable` over `GET /api/v1/erp-entries/vouchers`. The
grouped endpoint already returns **every** posting inside each group — the
filtering is entirely client-side, in one function:

```ts
function spendPostings(group) {
  const spend = group.entries.filter((e) => e.erp_account_type === 'expense')
  if (spend.length === 0 && group.entries.every((e) => e.erp_account_type === null)) {
    return group.entries          // connector declares no types → show everything
  }
  return spend
}
```

Everything downstream of it follows from that filter: expandability is measured
in spend postings, and the group's column is called Total because the surviving
rows sum to `VoucherGroupRead.amount`. Removing the filter is therefore not a
one-line change — it invalidates the reason those two were the way they were.

The per-posting figure already exists and is already correct:

```ts
postingAmount(entry)     // debit_amount − credit_amount, signed
basePostingAmount(entry) // the same in the company's currency, or null
```

## Goals / Non-Goals

**Goals:**

- Money movements (`payment`) never reach the client, from either listing.
- Every posting the API returns for a voucher appears when it is expanded.
- Each posting row carries its own `debit_amount − credit_amount`.
- A posting can be read against the invoice line it came from, and shows that
  line's spend category.
- The group's figure stops claiming to be a total of the rows beneath it.
- Keep the accordion — one page, one table, no view switching.

**Non-Goals:**

- No second view, no flat table, no `view` search parameter. An earlier draft of
  this change added an Entries/Vouchers toggle; it was dropped in favour of the
  accordion alone.
- No change to any request parameter, and none to the shape of
  `GET /erp-entries/vouchers` beyond `ErpEntryRead` gaining four additive
  response fields. One migration (0017), adding a nullable column.
- No running balance and no per-group debit/credit columns.

## Decisions

### `spendPostings()` is deleted outright, not parameterised

There is no longer a rule to apply — the group's `entries` are the rows. The
account-type fallback goes with it: it existed only to stop the filter from
emptying the table when a connector declares no types, and a filter that is not
there cannot empty anything. `erp_account_type` stays on `ErpEntryRead`; the
server's net-spend calculation still depends on it.

Alternative considered: keeping the filter behind a per-user toggle — that is
the view switch again, in a smaller box.

### Expandability is measured in postings, not spend postings

`postings.length > 1` becomes `group.entries.length > 1`. The old comment
justified the test by noting that "a typical purchase has one [spend posting],
so most rows do not expand" — with every posting shown, the opposite is true and
almost every voucher expands. That is the intended outcome, not a regression:
the ledger detail was already fetched and was simply unreachable.

The single-entry case keeps its existing treatment — no chevron, and the row
itself opens the drawer — so a lone voucherless posting is still reachable.

### The column becomes "Total Spend"

`VoucherGroupRead.amount` is unchanged: the server's net of the voucher's
expense postings. What changes is that its children now sum to zero instead of
to it, so a column called **Total** would be asserting an arithmetic that is
visibly false. **Total Spend** names what the figure actually is and stops it
reading as a column sum.

Alternatives considered and rejected:

- *Leave it as Total* — cheapest diff, but the header and the rows openly
  disagree and nothing on screen explains why.
- *Show `debit_total` instead* — reconciles against the credit rows, but it is
  the invoice's gross value, not spend, and the page is a spend product.

### The signed-amount helpers move to `#/lib/entry-amount.ts`

`postingAmount` / `basePostingAmount` are lifted out of `voucher-table.tsx`
unchanged. They have one caller today, but they encode the rule the whole page
turns on — the `?? 0` is load-bearing, because connectors send `0.00` rather
than null on the unused side and subtracting is what collapses two columns into
one signed figure without printing a zero. Keeping that in a named, testable
module rather than inline in a table component is the point.

### Payments are excluded in `_entry_conditions()`, the one shared chokepoint

`_entry_conditions()` already builds the WHERE clause for both the flat list and
the voucher groups — the module docstring calls it "the only place filters are
expressed, so the flat list and the grouped list can never drift apart". Adding
`entry_type NOT IN _EXCLUDED_ENTRY_TYPES` there means the two endpoints cannot
disagree about what exists, and the grouped endpoint gets it for free *before*
grouping, so a voucher of only payment postings produces no group rather than an
empty one.

It is an unconditional condition, not a default the caller can unset:
`entry_type=payment` composes with it and yields nothing. That is the intent of
"hard rule" — a query string should not be able to reintroduce a category the
product has decided it does not deal in.

**Not applied to `GET /erp-entries/{id}`.** That endpoint builds its own WHERE
and is left alone: it is reached from a link, and 404-ing a row that exists and
is in the caller's tenant would break a deep link to buy nothing, since no
listing hands out the id.

**Not applied to `reporting.py`.** The report endpoints are ledger reports;
silently changing `entries-summary` would move dashboard figures that nobody
asked to move, and `entries-by-account` would then have to follow for
consistency. The blast radius is not worth it.

That leaves one seam: the Entries page derives its entry-type filter options
from `entries-summary`, which still reports payments. Left alone, the filter
would offer a value guaranteed to return an empty table. So the frontend gets
`listableEntryTypes()` in `lib/entry-search.ts`, holding the excluded set as a
named constant with a comment pointing at the server rule.

Alternatives considered: exclude payments from `entries_summary` too, so the
options self-correct — rejected, it changes report semantics to fix a filter
dropdown. Or expose the excluded set over the API — rejected as an endpoint for
one string. Duplicating one constant, commented and tested on both sides, is the
smaller cost.

### The description field was never missing — the mock had nothing to put in it

`description` exists at every layer and always did: `ErpEntryData.description`
→ `ErpEntry.description` → `ErpEntryRead.description` → the Description cell on
each expanded posting row. The sync runner writes it, and the mock connector
maps it.

What was wrong was upstream, in the generator. `mock_erp/data/entries.py` netted
an invoice's lines per account before emitting:

```python
net_by_account[acct] = net_by_account.get(acct, 0.0) + ln["netAmount"]
...
description=f"{vendor_name} — {_account_name(acct)}"
```

Two consequences, and the second is the worse one. The line text was discarded,
so every expense posting read as a generic account label. And because
`_pick_lines` gives all of one invoice's lines the same account, `net_by_account`
always had exactly one key — so every invoice produced exactly **one** expense
posting. The accordion could never show more than one spend row per voucher, and
the "spend split across several expense accounts" case the old code was written
for could not occur in the data at all.

Emitting one posting per line fixes both: postings carry the line's own text,
and a voucher now has 3–5 postings instead of always 3. Reconciliation is
unaffected — the line net amounts already sum to the invoice net, so debit still
equals credit equals gross.

This is generator-only. No endpoint, DTO, model, or connector change, because
all of them already carried the field.

### The Type column goes, which also squares the header with the rows

With payments excluded server-side, what remains is overwhelmingly
`purchase_invoice`, so a Type column repeats one value down the page. It stays
in the drawer and as a filter, where it can still narrow something.

Removing it also fixes a real bug rather than only removing noise. The header
declared six columns (chevron, Voucher, Supplier, Date, Type, Total Spend) while
`EntryRow` spanned five (`1 + colSpan 2 + 1 + 1`), so every posting's amount
rendered under Type while the header called it Total Spend. Dropping Type makes
both five. A test now counts header columns against a posting row's summed
`colSpan`, so the two cannot drift apart again — that is the invariant worth
holding, not the specific number.

### The category is reached through the line, because that is where it lives

`ErpEntry` is never categorized — the result lives on `InvoiceLine`. So a Spend
category column on a posting needs a path from the posting to its line, and
there was none: an entry knew only its `source_invoice_id`, the whole invoice.

Resolving it by *matching* — description, amount, account — was the tempting
shortcut and is wrong: an ERP that nets several lines into one posting makes any
such guess silently incorrect, and two lines on the same account for the same
amount are indistinguishable. Instead the ERP's own line id is carried through
(`ErpEntryData.source_line_erp_id`) and the runner **derives** the row id:

```python
line_id = _det_id("line", source_invoice_id, entry.source_line_erp_id)
```

`_persist_invoices` builds the line's id from exactly that pair, so the two
agree by construction rather than by resemblance. The row is still confirmed to
exist before the FK is set, since a connector may reference a line its own scan
never delivered — and a dangling key would abort a whole sync over one posting.

**The FK points entry → line, many-to-one.** One invoice line can be posted
across several accounts, so several entries can share a line and then all read
the same category. `InvoiceLine` gains no reference back.

**Null is the ordinary case, twice over.** Most postings have no line at all —
input VAT, the payable, journal entries — and a line that exists may not be
categorized yet. The two render identically, and should: neither is a state a
reader can act on from an entry listing, and distinguishing them would only
invite the question "so which is it?" with no answer available on that screen.

Resolution happens in the single `_entry_select()` that builds every
`ErpEntryRead`, so the flat list, the voucher groups and the detail endpoint
cannot drift, and a client never fetches the line per row. The new columns are
appended after index 5, because `_net_spend` reads `erp_account_type`
positionally off that tuple.

### The account toggle now governs reading, not only fetching

`sync_enabled` gated `fetch_entries` and nothing else. Two facts make that
insufficient on its own: an account is **enabled when first discovered**, and
disabling one **deletes nothing**. So every tenant accumulates entries on
accounts the customer later switched off, and the listings kept showing them —
474 of 832 rows in the local database, across three accounts.

The condition goes in `_entry_conditions()`, the same chokepoint as the payment
exclusion, so the flat list and the groups cannot disagree and the groups get it
*before* grouping — a voucher left with no postings yields no group, and a
group's `entry_count` and totals never cover a row it does not show.

Expressed as a subquery, `erp_account_id IN (SELECT id FROM erp_accounts WHERE
sync_enabled)`, rather than a predicate on the account join: the same conditions
build the `select(count()).select_from(ErpEntry)` total, which has no join to
hang it on.

**Filtered, not deleted.** Deleting would reach the same screen today and be
irreversible; filtering means re-enabling an account restores its history with
no re-sync. That reversibility is the argument for it.

**Not applied to `reporting.py`**, on the same reasoning as the payment rule: the
reports stay ledger-complete and their figures do not move under a settings
toggle. This is a stated choice, not an oversight, and it is the point at which
a report placed beside the entries page would start to look inconsistent.

**Consequence**: with the VAT and payable accounts deselected, an expanded
voucher shows expense postings only, and its rows sum to the group figure again
instead of to zero. Both readings are correct depending on which accounts are
enabled, which is exactly why the column is named *Total Spend* rather than
*Total* — a name that is true in either configuration.

### The base amounts were frozen, which is what made the table lie

Renumbering the mock's entries surfaced a bug that had nothing to do with the
generator. `FxService.convert_row` short-circuited on:

```python
if row.fx_rate is not None and row.base_currency == base_currency:
    return UNCHANGED
```

That is only sound if a row's posted amounts never change once converted. But
entries are **upserted in place** under a deterministic id, and `_persist_entries`
rewrites `debit_amount`/`credit_amount` on every run. So a row whose content
changed kept the base amounts of the *previous* posting — and the entries table
renders the base amounts, so it showed a figure belonging to an unrelated row.
When the earlier posting had used the other side of the ledger, the sign flipped
too: an input-VAT debit displaying as a negative, a payable credit as a positive.

The fix is to test the invariant `convert()` already documents — "a stored base
amount must be reproducible from the stored original amount and the stored rate"
— rather than trusting the presence of a rate. Reproducibility is arithmetic
against the stored rate, so the short-circuit stays free of rate lookups, which
is what it existed for; `_eur_rates` is memoized per date anyway, so the lookup
was never the expensive part.

This also unbroke the repair path: `recompute_company` goes through the same
`convert_row`, so before the fix it reported every corrupt row as UNCHANGED and
repaired nothing.

Not covered, and stated rather than left implicit: a row whose amounts are
unchanged but whose *accounting date* moved to a day with a different rate still
short-circuits. Catching that needs a rate lookup per row, which would defeat the
optimization; it is a narrower case than a changed amount, and no connector in
this codebase does it.

### `nulls_last` on the flat list's ordering — kept as an independent fix

`GET /erp-entries` is not what this page calls, so this does not serve the
accordion. It is retained because it is a real defect on a public endpoint:
`accounting_date DESC` puts undated entries *first* in PostgreSQL (`NULLS FIRST`
is the default for descending), and `accounting_date, id` is not a total order
across equal dates in the presence of paging. New ordering:
`nulls_last(accounting_date DESC)`, `nulls_last(voucher_id)`, `id` — matching
what `/erp-entries/vouchers` already does for groups. `nulls_last` wraps the
voucher too because SQLite and PostgreSQL disagree on NULL placement in an
ascending sort.

## Risks / Trade-offs

- **The group figure and its rows no longer reconcile.** → The rename is the
  mitigation, and it is the honest one: the number is net spend, and now it says
  so. Anyone adding the rows gets zero, which is a self-evidently different
  quantity rather than a near-miss.
- **Almost every row now expands, so the collapsed table looks busier.** → Only
  the chevron is added; the rows themselves are unchanged until opened.
- **Three rows where there was one, once expanded.** → That is the request. The
  postings that appear are VAT and the counterparty, which are exactly what a
  reconciliation needs.
- **The ordering change affects other consumers of `GET /erp-entries`.** → The
  endpoint had no specified order before, so nothing could correctly depend on
  the old one; the change only makes the order stricter and total.
- **The excluded set is hardcoded in two languages.** A future exclusion has to
  be added in both `_EXCLUDED_ENTRY_TYPES` and `listableEntryTypes`. → Both
  carry a comment naming the other, and both are tested. The alternative was
  changing report semantics or adding an endpoint.
- **Listings and reports now disagree about what exists.** `entries-summary`
  counts payments; the entry lists do not. → Deliberate: reports are
  ledger-complete by design, the entries page is a spend view. Worth revisiting
  if a report is ever put beside the entry list in the same screen.
- **A payment is now unreachable through the UI.** If a customer needs to check
  a settlement, nothing surfaces it. → Accepted per the "hard rule" decision;
  `GET /erp-entries/{id}` still resolves one if its id is known.
- **The mock's entry count grows** — 832 postings where there were ~600, and
  entry numbers shift, so a re-sync writes new `_det_id`-derived rows rather
  than updating the old ones. → It is synthetic data behind a `--reset`-less
  runner; a fresh database is the intended way to pick up a generator change.
- **Existing rows keep frozen base amounts until repaired.** The code fix stops
  new ones appearing; it does not rewrite history. → `recompute-fx` (or the
  backfill CLI) now actually repairs them, because it shares `convert_row`.
- **The link only fills on a re-sync.** Migration 0017 backfills nothing —
  the source line is data only a connector can supply — so every existing row
  stays null until it is synced again. → Expected; the column reads empty, which
  is the same as "not categorized yet" and needs no explanation.
- **A real ERP may not report a line id at all.** Then the column stays empty
  forever for that connector. → Better than a matching heuristic that is
  confidently wrong; the absence is visible, a bad guess is not.
- **Real connectors may not post one line per invoice line.** Some ERPs do net
  by account, and then descriptions will be whatever that ERP wrote. → Nothing
  here depends on the one-to-one shape; it is the mock being more faithful, and
  the fallback description covers a line without text.

## Migration Plan

No data migration and no deploy ordering constraint — the two sides are
independent. Rollback is per-side: reverting the frontend restores the
spend-only expansion, reverting the ordering restores the previous unspecified
order.

## Open Questions

None. Two decisions were settled with the requester:

- The group figure stays net spend and is labelled **Total Spend**, rather than
  becoming the gross debit total or keeping the name Total.
- Money movements are excluded by `entry_type = 'payment'`, as a hard
  server-side rule, keeping credit notes and journal entries. *Not* by requiring
  a voucher number — payment vouchers carry one (the mock emits 8001, 8002…), so
  that test would not have excluded them.
