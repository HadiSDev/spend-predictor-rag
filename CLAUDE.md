# CLAUDE.md — Project Overview & Guidelines

## Project

**ERP Procurement Agent** — AI that ingests spend data, categorizes it against a
company's own spend tree, detects redundant suppliers, and suggests product-level
savings.

Two pipelines coexist:

1. **PDF pipeline** (original): `InvoiceFlow` — 5 CrewAI stages per PDF invoice
   (extract → verify → research_products → categorize → ledger CSV). Uses Qdrant
   for spend tree retrieval.
2. **Procurement pipeline** (new): batch processes structured transaction data
   from synthetic data or ERP connectors. Same categorization core, but outputs
   to PostgreSQL for aggregation, redundancy detection, and savings suggestions.

The code is split into two packages under `src/` (plus the standalone
`mock_erp/` server):

- **`web_api/`** — the **business domain**: SQLModel ORM + DB session + Alembic,
  ERP connectors, the Streamlit dashboard, and the Clerk-authenticated FastAPI
  backend. Owns persistence and the customer-facing API.
- **`ai_api/`** — the **AI workflows**: the PDF `InvoiceFlow`, RAG/Qdrant
  indexer, agents, the sync pipeline (runner + categorizer), aggregation,
  redundancy detection, and the recommender.

Dependency direction is one-way: **`ai_api` imports the domain from `web_api`**
(ORM models, DB session, connectors); `web_api` never imports `ai_api`.

## Environment

- Managed with Astral `uv`; **Python 3.12**.
- Install: `uv sync`
- Run PDF pipeline: `uv run main.py`
- Run sync pipeline: `python -m ai_api.sync.runner` (syncs **every connected
  `ErpIntegration`**; see below)
- Run document processing: `python -m ai_api.documents.runner` (reads each
  pending invoice's attached scan into invoice lines; a **separate** process
  from the sync — see below)
- Run web API: `uvicorn web_api.app:app --reload`
- Run dashboard: `streamlit run src/web_api/dashboard/app.py`
- Test: `uv run pytest`
- Migrate DB: `uv run alembic upgrade head`. The chain starts from **one
  squashed baseline** (`0001_baseline_schema`); the original 20 migrations never created
  a base table, so `upgrade` from empty had in fact never worked — the schema was
  built out-of-band by `create_all()`. A database that predates the squash is
  brought across once with `uv run alembic stamp 0001_baseline_schema --purge`
  (`--purge` because plain `stamp` first resolves the *current* revision, whose
  script was deleted). `tests/web_api/test_migrations.py` runs the chain from
  base against a throwaway PostgreSQL database, so this cannot silently rot
  again; it skips explicitly when no PostgreSQL is reachable.
- Infra: `docker compose up` (Qdrant on :6333, PostgreSQL on :5432)

## Web API auth (Clerk)

- The web API (`web_api/`) is a resource server: it verifies Clerk session JWTs
  against Clerk's JWKS. Set `CLERK_ISSUER` (JWKS URL derives from it) and
  optionally `CLERK_AUDIENCE` in `.env`. `WEB_API_AUTH_DISABLED=true` bypasses
  verification for local dev. See `.env.example`.
- **Verification allows `CLERK_CLOCK_SKEW_SECONDS` (default 5) of clock skew**,
  and must: `iat` is stamped on Clerk's clock and checked against this host's,
  so PyJWT's default zero tolerance rejects a good token with *"The token is not
  yet valid (iat)"* whenever the local clock runs behind — an intermittent 401
  that succeeds on retry, and a confusing one because nothing is wrong with the
  token. 5s matches Clerk's own backend SDK. The leeway widens `exp` by the same
  amount, so it stays small; `tests/web_api/test_auth.py` pins both halves —
  skewed token accepted, genuinely expired token still rejected.
- API docs use **Scalar** at `/scalar` (built-in Swagger/ReDoc disabled;
  OpenAPI JSON at `/openapi.json`).
- **CORS** for a browser front-end is opt-in via `WEB_API_CORS_ORIGINS`
  (comma-separated; empty = no cross-origin access).
- **Clerk sync**: `POST /api/v1/webhooks/clerk` receives Svix-signed Clerk events
  (org / membership / user) and applies them idempotently — `organization.deleted`
  **soft-suspends** (retains all data; suspended orgs are blocked from API access
  until restored). Suspending/deleting an org locally (`DELETE /api/v1/organization`,
  admin) propagates to Clerk via the Backend API. Env: `CLERK_WEBHOOK_SIGNING_SECRET`,
  `CLERK_SECRET_KEY`, `WEB_API_CLERK_OUTBOUND_DISABLED` (default true off-prod).
  Register the webhook in the Clerk dashboard → `/api/v1/webhooks/clerk`.

## Web API roles & endpoints

- **Roles** (org role from Clerk): `admin`, `moderator`, `member`, `viewer`.
  Plus a platform-level `User.is_system_admin` set from a Clerk claim named by
  `CLERK_SYSTEM_ADMIN_CLAIM` (default `system_admin`).
- **Write access** to management endpoints = system admin OR org `admin`/`moderator`
  (`require_management`); org-profile updates require system admin OR `admin`
  (`require_org_admin`). `member`/`viewer` are read-only. System admins act
  across organizations.
- **Endpoints**: read — `GET /users/me` (current principal), `/users` (org member
  directory), `/vendors` (the org's referenced suppliers, `?q=`),
  `GET /companies` (`?include_inactive`; each carries its `base_currency`), `/invoices`,
  `/invoices/{id}`, `/invoice-lines` (filters: `status`/`company_id`/`vendor_id`/
  `voucher_id`/`origin`/`stale`/`from`/`to` — the last four resolve through the line's
  invoice, since a line carries no date, supplier or voucher of its own),
  `/invoice-lines/{id}/audit`, `/erp-entries`
  (filters: `company_id`/`entry_type`/`voucher_id`/`source_invoice_id`/`status`/
  `from`/`to`/`vendor_id` — `from`/`to` bound `accounting_date`, and `vendor_id`
  resolves through the entry's source invoice, so unlinked postings never match;
  ordered `accounting_date` desc with undated last, then `voucher_id`, then `id`,
  so a voucher's postings stay adjacent and pagination is stable),
  `/erp-entries/vouchers` (the same rows **grouped by voucher**, paginated over
  groups so a voucher's postings are never split across a page; a null
  `voucher_id` forms a group of one, and a group's `currency`/vendor are null
  when its entries disagree). **Both entry listings exclude `entry_type=payment`**
  (`_EXCLUDED_ENTRY_TYPES` in `_entry_conditions()`): a payment settles an
  invoice already accounted for, so it is noise in a spend tool. It is a product
  rule, not a default — `?entry_type=payment` returns an empty page — and it is
  narrow: `credit_note` and `journal_entry` both move real spend and stay.
  **Both listings also exclude entries on accounts with `sync_enabled=false`** —
  the toggle gates the fetch, but accounts are enabled when discovered and
  disabling one deletes nothing, so deselected accounts otherwise keep showing.
  Filtered, not deleted: re-enabling restores the history with no re-sync.
  `GET /erp-entries/{id}` is **not** gated (a lookup, not a listing), and
  `reporting.py` is untouched, so the reports stay ledger-complete; that is why
  the frontend filters `payment` out of its entry-type options
  (`listableEntryTypes`). Then `/erp-entries/{id}`, `/erp-integrations`, `/erp-integrations/{id}`,
  `/erp-integrations/{id}/accounts` (the chart of accounts; readable by any
  authenticated member, writes are management-gated), the **voucher detail**
  quartet — `GET /erp-entries/vouchers/{voucher_id}`, `/erp-entries/vouchers/`
  `by-entry/{entry_id}` (the same voucher addressed by one of its postings, for
  a link that names an entry), and each one's `/audit` sibling —
  `GET /invoices/{id}/document` (streams the scan **live from the ERP**; nothing
  is copied locally, so there is no second copy to keep in sync), `/erp-types` (the connector catalog:
  which ERP systems this deployment supports and the credential fields each
  declares — authenticated, not management-gated), `/organization`, and **reports** —
  `GET /reports/entries-summary`, `/reports/entries-by-account`,
  `/reports/spend-by-category`, `/reports/spend-by-vendor` (all accept
  `company_id` + `from`/`to`; entries reports also `entry_type`). Manage — `POST /companies`
  (**requires a `base_currency` and an `integration` block**: the company, its
  `ErpIntegration`, and its encrypted credential are written in one transaction,
  so a company is never left without an ERP connection; the response is the
  company plus its integration),
  `PATCH /companies/{id}` (carries `spend_tree_id`; changing it reassigns and
  reports the affected line count), `POST /companies/{id}/deactivate|activate`,
  `POST /companies/{id}/recompute-fx` (rewrite stored base amounts),
  `POST /companies/{id}/recategorize` (return the company's `ai_failed` lines to
  `uncategorized` so the next sync's categorizer retries them — it **queues**,
  it does not categorize: `web_api` cannot import `ai_api`, so the response
  reports lines queued, never lines categorized; only `ai_failed` is eligible,
  and origin is deliberately not a filter),
  `POST /invoice-lines/{id}/verify` (accept or correct the categorization),
  `POST /invoices/{id}/reprocess` (queue the attached scan to be read again —
  409 with no document or while `processing`; see Document processing),
  `PATCH /invoices/{id}` (correct the parsed header — **not gated on
  provenance**; see Invoice corrections),
  `POST /invoices/{id}/verify` (correct **and** mark the header human-verified),
  `PATCH /invoice-lines/{id}` (correct `description`/`quantity`/`unit`/
  `unit_price`/`amount` — a categorization field or `native_account_code` here
  is a `422`), `POST /invoices/{id}/lines` (add one), `DELETE /invoice-lines/{id}`,
  `PATCH /organization`. **ERP integrations** — `POST /erp-integrations` (with
  credentials), `PATCH /erp-integrations/{id}`, `POST /erp-integrations/{id}/`
  `disconnect|reconnect|test-connection|refresh-accounts|replace` (management-gated;
  `replace` moves the company to a different ERP — `PATCH` cannot change
  `erp_type` — and `409`s with the counts a switch would double until
  `confirm: true`), `PATCH /erp-accounts/{id}`
  (toggle `sync_enabled`/`with_vat`). **`sync_enabled` and `with_vat` are
  customer settings, not ERP metadata**: the ERP's value seeds a newly
  discovered account, and from then on neither `refresh-accounts` nor the sync
  runner may overwrite them — both upsert sites refresh only name, type, parent
  and `is_active`. `sync_enabled` governs **both** what the sync fetches and what
  the entry listings return. `with_vat` records whether an account is *assumed* VAT-
  inclusive, which is what lets reconciliation tell a VAT difference from a
  total difference; it recomputes no stored amount. Managed from
  `/settings/companies/$companyId/accounts` in the frontend. Both creation paths share
  `web_api/integrations.py` (`provision_integration` adds without committing, so
  the caller owns the transaction) and validate credentials against the
  connector's declared `credential_fields` — required ones must be present,
  undeclared keys are rejected. An integration's `erp_type` is **fixed once
  connected** (`PATCH` takes label + credentials only), and credentials are
  write-only: the API returns no values, and supplying `credentials` replaces
  the whole map, so a client can only replace them wholesale, never edit one.
  Moving a company to a different ERP is `POST /erp-integrations/{id}/replace`,
  which soft-disconnects the old integration and provisions the new one in **one
  transaction** — composed client-side, a failure between disconnect and create
  would leave the company connected to nothing. The old integration's accounts,
  entries and invoices are kept, which is why the endpoint **409s with the
  counts it would double** (entries, invoices, and the date span, joined through
  `ErpAccount` since neither `ErpEntry` nor `Invoice` names an integration)
  until `confirm=true`: the new ERP re-delivers overlapping periods as separate
  rows and no report can tell them apart. The same `erp_type` is a `422`
  pointing at `PATCH` — replacing would only retire the integration and restart
  its sync from scratch. Integration credentials are stored encrypted
  (`WEB_API_CREDENTIAL_ENC_KEY`, Fernet) and never returned; no credential row is
  written when none are supplied, so a connector whose fields all have defaults
  needs no encryption key. Integrations are soft-disconnected. Companies are
  soft-deactivated, never hard-deleted.

## Categorization lifecycle & audit

- **Result lives on the line.** `InvoiceLine` holds its categorization result
  directly (`level_1/2/3/4`, `account_code`, `account_name`, `confidence`,
  `rationale`, plus the accepted `spend_category_id`) — there is no separate
  `LineCategorization` table. `level_4` is set only on a four-level tree.
- **Line status**: `uncategorized` → `ai_failed` | `ai_categorized` → `verified`.
  The AI sync runner writes the result and sets `ai_categorized`/`ai_failed`; a
  human `POST /invoice-lines/{id}/verify` (management role) sets `verified`,
  optionally correcting the category.
  **`ai_failed` is not terminal.** `_categorize_pending` processes only
  `uncategorized` lines, so a failure used to survive every re-sync and backfill
  — an improved categorizer could never reach the backlog it had already lost.
  `POST /companies/{id}/recategorize` is the one transition that moves a line
  *backwards*, audited as `requeued_for_categorization` (actor `system`) and
  clearing the stale `error_message`. Nothing else may: a sync still never
  resets a failure on its own. `Invoice.status` is a **rollup** of its
  lines (`uncategorized` → `categorized` → `verified`), recomputed in the same
  transaction as any line change (`web_api/rollup.py`).
- **Audit** (`web_api/audit.py` + generic `AuditLog` table): every AI
  categorization and human verify/edit appends an append-only row
  (`entity_type`, `entity_id`, `action`, `actor` — a user id or `system` —,
  field-level `changes`). One table for both invoices and lines.
- **Ground truth is ai_api-only.** Synthetic `gt_*` values live in the
  ai_api-owned `line_ground_truth` store (`ai_api/persistence/`), never on the
  domain line. For real data, a `verified` line's values are treated as truth.
- **Origin never changes categorization.** A `document_ai`, `erp` and
  `entry_fallback` line all move through the same lifecycle and all count in the
  reports. A stand-in line's spend is real spend, and withholding it pending a
  document that may never arrive would leave most of the ledger uncategorized.
- **A category is chosen, never typed.** `POST /invoice-lines/{id}/verify` takes
  a `spend_category_id` and derives `level_1..level_4` from that node's path,
  ignoring any levels sent alongside; a node outside the company's assigned tree
  is a `422`. Free text produced a categorization resolving to nothing, which is
  precisely what the stored pointer exists to prevent — so the frontend's line
  editor is a tree selector, not four inputs.
- **`category_stale` is computed, never stored**: any level set and no
  `spend_category_id`. It means the line's decision no longer resolves in the
  company's tree — visible on every line payload and filterable
  (`GET /invoice-lines?stale=true`). Distinct from `ai_failed`: nothing failed,
  the taxonomy moved.

## Spend trees (the target taxonomy)

- **A `SpendTree` belongs to an `Organization`; a `Company` points at the one it
  categorizes against** (`Company.spend_tree_id`). Several companies may share a
  tree — a bookkeeping firm wants one taxonomy across its clients — and one org
  may hold several. A tree from another organization is a `404`.
- **`SpendCategory` is a node of a tree, not a column bag hanging off a
  company.** It carries `spend_tree_id`, `parent_id`, `depth`, `name`,
  `sort_order` and an optional `code`, **and** keeps `level_1..level_4` as the
  **materialized path**. Both are load-bearing: parentage is what makes renaming,
  reparenting and depth enforcement possible; the path keeps every existing read
  working without a recursive query and — the real reason — lets an
  `InvoiceLine` keep its decision when the node it pointed at is gone.
  `spend_categories.company_id` no longer exists.
- **`web_api/spend_trees/service.py` is the only writer of `SpendCategory`.**
  Nothing else may write it: a rename rewrites every descendant's path in the
  same transaction, and an ORM write straight to the table silently desyncs the
  two representations. Nothing there commits — the caller owns the transaction.
- **The default tree is a code-resident template** (`spend_trees/template.py`,
  three levels, `Direct`/`Indirect` at level 1), **copied into an org on first
  use** by `ensure_default_tree()` — idempotent per org, so an org holds at most
  one copy. A customer edits their copy freely; the template and other tenants
  are untouched. `POST /companies` assigns it when no `spend_tree_id` is given,
  in the same transaction as the company. **`POST /spend-trees/default` exists
  because that was otherwise the only trigger**: an org whose companies predate
  spend trees could not obtain the default at all. It is idempotent and returns
  `200`, and the settings page + company picker only offer it while no copy
  exists.
- **A tree is deleted hard, a company is deactivated soft** — the asymmetry is
  deliberate: a company owns financial records, a tree owns none, since a line
  keeps its `level_*` whatever happens to the node it pointed at. `DELETE
  /spend-trees/{id}` is refused while a company is assigned (reassign first) and
  `409`s with a count when categorized lines point into it, until `confirm=true`.
  `/archive` remains the gentler option: retired from the pickers, history
  reachable.
- **`max_depth` lives on the tree** (3 or 4; `default_template` is pinned to 3)
  rather than being derived from the deepest node, so the editor can gray out
  "add child" *before* the user tries. Over-deep writes are `422`; lowering it
  below existing nodes is refused.
- **Three authoring paths, one result**: clone, empty, or CSV import
  (`level_1..level_4`, `description`, optional `code`). An import is **validated
  wholly and applied wholly** — one bad row rejects the file with a per-row
  report and changes nothing. A `replace` that would orphan categorized lines is
  a `409` with the count until `confirm=true`.
- **Changing a company's tree costs no categorization work.** In the same
  transaction as the `PATCH`, lines whose stored path exists in the new tree are
  re-pointed (**exact, case-sensitive, whole-path** — fuzzy matching is the
  guessing the sync's derived entry→line link refuses); the rest have only
  `spend_category_id` cleared, keep every level, status and rationale, and get an
  `AuditLog` row (`spend_tree_reassigned`, actor `system`). The response reports
  the affected count, because the caller must learn the consequence where they
  cause it. Nothing is requeued and no verification is discarded.
- **The categorizer's candidates are the assigned tree's leaves** — interior
  nodes are headings, and matching to one throws away the precision the customer
  built the tree for. **No tree ⇒ no categorization**: lines stay
  `uncategorized`, the reason lands on the integration's `SyncState`, the ledger
  still persists and the watermark still advances. There is deliberately no
  fallback taxonomy. `_META` is gone from `ai_api`; the template is its
  successor, and its curated keywords attach to template-seeded nodes by `code`
  (a custom node matches on its own name/description — a weakness of the
  *keyword stub*, which the embedding categorizer removes).
- Endpoints: `GET /spend-trees` (+ `?include_archived`), `GET /spend-trees/{id}`
  (whole tree in one response — the selector's navigation and search are only
  instant if the client holds it), `POST /spend-trees` (clone or empty),
  `POST /spend-trees/default`, `PATCH`, `DELETE` (+ `?confirm`), `/archive`
  (both refused while assigned), `/import`, plus
  `POST /spend-trees/{id}/nodes`, `PATCH|DELETE /spend-tree-nodes/{id}`. Reads
  are open to any member — a reviewer picking a category needs the tree; writes
  are management-gated. Managed at `/settings/spend-trees`.
- `ai_api/rag/indexer.py` gained `build_tree_index`/`retrieve_categories`, keyed
  by **tree id**, alongside the older CSV-and-tenant pair the PDF `InvoiceFlow`
  and synthdata still use. Not yet wired into the sync (its stub matcher needs
  no embeddings).

## Invoice corrections (what a human may fix, and what protects it)

- **Corrections are applied in place, and the audit trail is the only record of
  what was there before.** There is no shadow column holding the ERP's or the
  extractor's figure: `AuditLog`'s `old` value is it. Every correctable field is
  therefore in `INVOICE_AUDIT_FIELDS` / `LINE_VALUE_AUDIT_FIELDS`
  (`web_api/audit.py`) — one omitted there is one whose original is gone.
- **`verified_fields` is what stops a sync overwriting a correction**, on both
  `Invoice` and `InvoiceLine`. **Per field, not per row**, and that is
  load-bearing: a row-level flag would freeze the invoice against the ERP
  entirely, so a reviewer fixing a typo'd invoice number would also stop a
  genuine later re-posting of the total from ever reaching us. `_persist_invoices`
  assigns through `_assigner()`, which skips a settled field; `--hard-reset` is
  the one override, audits each overwrite as actor `system`, clears the mark, and
  does **not** delete human-added lines. Written only through
  `web_api/verified.py` — it assigns a new list, because SQLAlchemy tracks a JSON
  column by identity and an in-place `.append()` is silently dropped.
- **Verification is a distinct action from a correction.** `POST
  /invoices/{id}/verify` mirrors `POST /invoice-lines/{id}/verify`. It exists
  because "I read this and it was right" is a signal a PATCH cannot express, and
  it is the label the extractor learns from. The fields marked are the ones the
  caller **sent**, not the ones that changed — resubmitting an already-correct
  total is a human asserting that figure. The audit action is then `verify`
  (nothing moved), while `noop` stays the PATCH vocabulary.
- **The supplier is corrected two ways, and neither writes the catalog.**
  `Vendor` is **global**, so a write-through would rewrite the supplier for every
  other tenant. Re-pointing `vendor_id` says "wrong supplier"; the invoice's own
  `supplier_name`/`supplier_country_code`/`supplier_vat_number` say "this
  supplier's details are wrong on this document". Payloads carry the resolved
  value (`override ?? vendor.value`) plus `supplier_overrides` naming which are a
  human's. Consequence, accepted: `/reports/spend-by-vendor` still groups by
  `vendor_id`, so a name override moves no spend — the re-point is for that.
- **A category is never corrected through `PATCH /invoice-lines/{id}`** — that
  is a `422`, not a silently dropped field, because an ignored `spend_category_id`
  reads to the caller as a category edit that did nothing. `native_account_code`
  is likewise refused: it is the ledger's own statement of where the money went.
- **Deleting a line is hard, and audited.** A soft-delete flag would have to be
  understood by the reports, the categorizer, the reconciler and the entry
  payload's category resolution, and one that forgot would double-count. The
  audit row carries the line's values and categorization instead. Its postings
  survive with `source_invoice_line_id` nulled — the same thing extraction does.
- **Reconciliation warns, never blocks.** `web_api/reconcile.py` owns the rule
  (`max(1%, 1.00)` against `total` or `total − tax`) and **both** the document
  stage's accept/reject and `InvoiceDetailRead.lines_reconciled` /
  `reconciliation_delta` use it, so an extraction accepted as reconciling is
  never then reported to a reviewer as not reconciling. Computed on read, never
  stored — the same reasoning as `category_stale`. Extraction still *rejects*: a
  model producing lines that do not add up has no reviewer behind them, whereas a
  human mid-way through a multi-line fix must not be blocked by their own
  unfinished work.
- **A correction clears what it invalidates, and never reconverts inline.**
  Correcting `currency`/`total`/`tax` nulls the invoice's base figures;
  correcting a line's `amount` nulls the line's. The cleared fields ride in the
  same audit entry. `POST /companies/{id}/recompute-fx` is the way back.
- **Automatic extraction yields to human work.** A sync will not queue an invoice
  whose lines include a `verified` or `human` one — replacement is whole-invoice
  and would discard it. `POST /invoices/{id}/reprocess` still proceeds: a human
  asking is a decision, and the per-line audit rows are the record.

## Invoice lines: the unit of spend

- **The Entries page lists invoice lines, not postings.** A posting is what the
  bookkeeper wrote; a line is what was bought, and only a line carries a
  description, a category and a human's verification. Vouchers remain the
  grouping and expand into their lines; the postings stay on the voucher panel's
  **Postings tab** as ledger evidence.
- **`InvoiceLine.origin`** is `human` | `document_ai` | `erp` | `entry_fallback`,
  in that precedence. A person who read the document outranks a model that read
  it; the document is the only source that knows what was bought; the ERP's bill
  lines are its own statement of the voucher; a posting is the floor.
  **An invoice holds exactly one *automated* origin at a time** — two would
  describe the same spend twice and double its total. `human` is the deliberate
  exception: a reviewer splitting a stand-in adds real lines beside it and then
  deletes it, and forbidding the intermediate state would make the operation
  impossible one step at a time — the reconciliation warning covers it instead.
  A `human` line is never refreshed or removed by a sync or an extraction, which
  is true by construction (the connector keys lines by `_det_id`, and a human
  line's fresh UUID cannot collide). Stored, never inferred: a stand-in line and
  an extracted line can be identical in every other field, and the difference is
  whether anyone read the document.
- **Stand-in lines.** When no better source produced one, the sync writes one
  line per **expense** posting (`EXPENSE_ACCOUNT_TYPE` in `db/models/enums.py` —
  the *same* constant the voucher's Total Spend is netted from, so the lines and
  the figure above them count the same postings). VAT, the payable and the rest
  never become lines: an invoice's lines would then sum to zero.
- **`InvoiceLine.unit`** is what `quantity` counts (`pcs`, `hours`). A bare
  quantity is ambiguous — `12` against "Consulting" is twelve hours or twelve
  days — and unit prices cannot be compared across suppliers without it. Null is
  the ordinary case and is **never defaulted**: a Billy bill line carries a
  quantity and no unit field at all, and a posting has neither, so in practice
  only the document states one.
- **`Invoice.document_invoice_number`** is the supplier's number as read off the
  scan, stored **beside** the as-posted `invoice_number`, which extraction never
  rewrites — the same rule that keeps `base_total` beside `total`. Load-bearing
  because the as-posted value is frequently not an invoice number at all:
  Billy's `suppliersInvoiceNo` is user-entered and often null and `voucherNo` is
  blank at least as often, so `_map_bill` falls back to the bill id (on the dev
  org the stored numbers are Billy's own voucher sequence — `29`, `18`, `16`).
  The Entries table prefers the printed number and keeps the posted one reachable
  when they disagree, because a disagreement means the ERP's is wrong or the scan
  belongs to another invoice.
- **`InvoiceLine.sequence`** is the position its source stated. The row id is a
  random UUID, so ordering by it alone scrambles a document — invisible while the
  page listed postings, wrong the moment it lists lines. `id` is the tiebreak.
- **`GET /erp-entries/vouchers` carries each voucher's lines** (batched, one
  query) plus its invoice's `doc_status`/`doc_error` and **both** invoice
  numbers — which to show is presentation, and collapsing them server-side would
  throw away the disagreement. Additive only: grouping,
  pagination and `_voucher_amount()` are untouched, and the group's figure stays
  the net of its expense postings — never a sum of the lines, which may
  legitimately differ.

## Document processing (`ai_api/documents/`)

- **A stage of its own**, not a step in the sync: `python -m ai_api.documents.runner`
  (`--company-id` / `--invoice-id` / `--limit`). It discovers `doc_status='pending'`
  invoices from the database exactly as the sync runner discovers integrations —
  no tenant, no credentials as arguments — oldest `invoice_date` first. Extraction
  is LLM-bound and fails for reasons unrelated to the ERP; inlining it would stall
  the ledger behind a model outage.
- **`Invoice.doc_status`** is `not_applicable` | `pending` | `processing` |
  `processed` | `failed`, plus `doc_attempts` / `doc_error` / `doc_processed_at`.
  **Distinct from `Invoice.status`**, the categorization rollup: one says whether
  we read the document, the other whether the spend is categorized.
  `not_applicable` (no scan) is the ordinary case, not a failure.
- **Claim before work.** The stage commits `processing` before fetching, so two
  overlapping runs cannot both take an invoice. `doc_processed_at` doubles as the
  claim timestamp; a claim older than `DOC_STALE_CLAIM_MINUTES` is re-taken, so a
  run that died holding one does not strand the invoice.
- **The sync queues, never processes, and is not a retry.** A `processed`,
  `processing` or `failed` invoice is left alone by a sync; only a *different*
  document requeues a processed one. The way back from `failed` is
  `POST /invoices/{id}/reprocess` (management), which also resets the attempt
  count — the ceiling is what stopped the stage, and a human asking is new
  information. It 409s with no document, or while `processing`.
- **An extraction that does not reconcile is rejected**, not flagged. The lines
  must sum to the invoice's `total` *or* its `total − tax` (documents state
  either; `ErpAccount.with_vat` describes the account, not the document) within
  `max(1% , 1.00)`. Lines that miss a line would be categorized, aggregated and
  surfaced as a savings opportunity with nothing downstream able to tell they
  were wrong. A rejection keeps the invoice's existing lines.
- **Replacement is whole-invoice, in one transaction, and audited.** Every
  removed line gets an `AuditLog` row (`superseded_by_extraction`, actor
  `system`) carrying its categorization — the only record a human's verified
  category ever existed. Verification is not yet a platform affordance that can
  protect a line, so extraction wins and the audit row is the groundwork.
- **Postings are unlinked by replacement.** An extracted line has no ERP line
  identity, so relinking would mean matching on amount — the guessing the sync's
  derived link refuses. A posting on an extracted invoice therefore shows no
  spend category, which is acceptable only because the category moved to where
  the reader looks.
- **No bytes are persisted.** The scan is fetched live per run through
  `web_api/documents.py::resolve_document_source` — the same rule
  `GET /invoices/{id}/document` uses, shared so the two cannot disagree about
  which voucher holds it. Dispatch is on the ERP's declared media type: a JPEG
  receipt records a clean unsupported-media failure rather than "Invalid PDF
  structure" over a perfectly good document. **A vision model is not yet wired
  in**, so images and text-layerless PDFs fail cleanly and keep their stand-ins.
- Env: `DOC_MAX_ATTEMPTS`, `DOC_RECONCILE_TOLERANCE_PCT`,
  `DOC_RECONCILE_TOLERANCE_ABS`, `DOC_STALE_CLAIM_MINUTES`.

## Vendors (global supplier catalog)

- `Vendor` is a **global** supplier database (`name`, `country_code`,
  `vat_number`, `description`) — **not** company/org-scoped and carrying no ERP
  identity. Identity/dedup on sync is **VAT number, else normalized name**
  (`ai_api/sync/runner.py:_vendor_key`); the same supplier seen by different
  companies collapses onto one row.
- Only `Invoice.vendor_id` references a vendor. Invoice **lines do not** link to
  a vendor, and the vendor holds no back-reference to invoices/lines.

## Reporting

- Read-only, tenant-scoped aggregates live in `web_api/reporting.py` (pure SQL
  `GROUP BY`) behind `web_api/routers/reports.py`. **Ledger sums are
  entry-based** (`entries-summary`, `entries-by-account` over `ErpEntry`);
  **category/vendor spend comes from the invoice layer** (`spend-by-category`
  from categorized lines, `spend-by-vendor` from invoices) — entries carry no
  category/vendor. Money is always **grouped by a currency column**, never summed
  across currencies. Not built in `ai_api/aggregation` (that stub is
  pipeline-internal; `web_api` can't import `ai_api`).
- Every report — and `GET /erp-entries/vouchers`, whose group totals are also
  sums — takes **`currency_mode=base|original`, defaulting to `base`**: `base`
  groups by the stored `base_currency` and sums the converted amounts (one row
  per dimension, in the customer's currency); `original` groups by the as-posted
  `currency` and reproduces the pre-conversion behaviour exactly. Unconverted
  rows have a null `base_currency`, so in base mode they form their own row —
  null currency, zero totals, `unconverted_count` set — rather than being folded
  into a total they don't belong in or dropped so it understates spend.

## Currency conversion (company base currency)

- **Every `Company` has a `base_currency`** (ISO 4217, required at creation,
  editable in Settings). It is a customer setting like `sync_enabled`: no
  connector, sync, or refresh may overwrite it.
- **Amounts are converted at the rate in force on the transaction's own date**,
  never today's — `Invoice.invoice_date`, `ErpEntry.accounting_date`, and a line
  follows its invoice. `Invoice`, `InvoiceLine` and `ErpEntry` each store
  `base_currency`, base amount column(s), `fx_rate` and `fx_rate_date` **beside
  the as-posted columns, which are never rewritten** — they are the evidence.
  `fx_rate` is base-per-1-posted, so `base = amount × fx_rate` reproduces the
  stored figure exactly. A same-currency row still converts, at rate 1.
- **No date, no rate, or no network ⇒ stored unconverted** (all base fields
  null), never converted at a substitute rate. FX failures never fail a sync:
  the ledger data lands and the watermark still advances.
- `web_api/fx/` — `provider.py` (ECB daily reference rates via Frankfurter,
  behind a one-method seam tests stub), `service.py` (`FxService`: rate
  resolution, per-run memo, row conversion), `recompute.py`, `backfill.py`.
  Rates cache in `fx_rates` **against EUR**, so any pair is derived as
  `rate(EUR→B)/rate(EUR→A)`; a non-publication date (weekend/holiday) resolves
  **backwards** and the row records `published_date`, so a Saturday is cached
  without passing a lookup date off as a publication.
- Env: `FX_ENABLED` (**default false** — tests and offline runs make no outbound
  request), `FX_PROVIDER_URL`, `FX_HTTP_TIMEOUT_SECONDS`.
- **Changing a company's base currency does not rewrite history inline.** Rows
  are rewritten by `POST /companies/{id}/recompute-fx` (management) or
  `python -m web_api.fx.backfill [--company-id …]`, each row at its *own*
  historical rate. In between, reports show two `base_currency` rows — visibly
  stale, not silently wrong.

## ERP entries

- `ErpEntry` is the atomic financial record (raw GL posting), never categorized.
  Its ledger date is `accounting_date` (the posting date; the axis for period
  reporting). It carries **no** direct `erp_integration_id` — the integration is
  reached through its account (`erp_account_id → ErpAccount.erp_integration_id`);
  `company_id` gives tenant scope. The sync scopes an integration's entries by
  joining through `ErpAccount`.
- `ErpEntry.source_invoice_line_id` links a posting to the **invoice line** it
  was posted from — **many entries → one line**, since a line can be posted
  across several accounts. Nullable, and null is the ordinary case: input VAT,
  the payable, journal entries and payments belong to a whole voucher, not a
  line. It is set only when the connector states the line
  (`ErpEntryData.source_line_erp_id`) and is **derived**, never matched — the
  runner rebuilds the line id from the same `(invoice, line_erp_id)` pair
  `_persist_invoices` used, so the two agree by construction; a reference to a
  line the scan never delivered is stored as null rather than aborting the sync.
  The entry is still never categorized: the category lives on the line and is
  only *read through* this link.
- `ErpEntryRead` **resolves the account and the supplier server-side**
  (`erp_account_code`/`erp_account_name`, `vendor_id`/`vendor_name`) — an entry
  carries only foreign keys, and the vendor is not even one of them (it is
  reached via `source_invoice_id → Invoice.vendor_id`), so a client would
  otherwise need three lookups per row. It also carries
  `source_invoice_line_id` and `spend_category_level_1/2/3`, read off the linked
  line — all null when there is no line, and the levels also null when the line
  is not categorized yet (the two are deliberately indistinguishable). `web_api/routers/erp_entries.py` builds
  every entry payload through one `_entry_select()`/`_entry_read()` pair and
  every filter through one `_entry_conditions()`, so the flat list, the voucher
  groups, and the detail endpoint cannot drift apart.

## Voucher detail panel

- One **URL-addressable** side panel on `/entries`, driven by search params
  (`?voucher=` / `?entry=` / `?tab=`) so a pasted link opens the same voucher on
  the same tab for whoever receives it. `by-entry` exists for the second form:
  a link that names a posting still opens its whole voucher.
- **Role decides affordance; provenance only informs.** Every parsed field —
  the invoice header, the supplier, and a line's values and category — is
  correctable by a management role, whatever `Invoice.source` says. A read-only
  role sees the same values as flat evidence text, never a disabled input,
  because a disabled input claims a permission that will never be granted.
  **Postings remain uncorrectable for everyone**: an `ErpEntry` is the ledger's
  own record, and nothing in the panel edits one. `Invoice.source` still rides
  along as a badge — it says how much to trust a value, not whether it may be
  changed.
- **An attached document is not necessarily a PDF.** The viewer dispatches on
  the blob's own media type — PDF through pdf.js, `image/*` as a plain `<img>`,
  anything else as a download rather than a broken preview. Real Billy
  attachments include JPEG photos of receipts, and handing one to pdf.js
  produces "Invalid PDF structure" over a document that is perfectly fine.
  The type comes from the ERP's file record, so it is never guessed.
- Correcting `currency`/`total`/`tax` **nulls that invoice's base amounts**
  rather than keeping figures derived from values that no longer exist — the
  same "visibly stale, not silently wrong" rule the FX section states.
  `POST /companies/{id}/recompute-fx` restores them.
- The panel's header total comes from the server, via the very same
  `_voucher_amount()` the voucher *groups* use, and honours `currency_mode`.
  Summing the embedded entries client-side would show a different number **and a
  different currency** from the row the panel was opened from.
- `AuditLog.seq` is a **DB-generated** monotonic column (a PostgreSQL sequence,
  `server_default=FetchedValue()`) because the voucher-wide audit feed orders by
  insertion, and a same-transaction timestamp tie is otherwise unordered.
  `FetchedValue()` is load-bearing: it makes the ORM **omit** `seq` from the
  INSERT so the sequence default applies. `default=None` instead sends an
  explicit `NULL` and every audit write fails on PostgreSQL — invisible to the
  SQLite suite, so change this only with a PostgreSQL check that goes **through
  the ORM**, not raw SQL.

## Sync pipeline

- **The runner reads its work from the database, never from arguments.**
  `run_sync()` takes no tenant and no credentials: it syncs every
  `ErpIntegration` with `disconnected_at IS NULL`, taking `company_id` and
  `erp_type` off the row and decrypting that integration's own `ErpCredential`
  for the connector config. No credential row means the connector's declared
  field defaults — the normal case for the Debug ERP.
- **The runner never creates an Organization, Company, or ErpIntegration.**
  Those come from the frontend (`POST /companies` with its `integration` block).
  A company created in Settings is picked up by the next run with no code or
  flag change. Consequence: a cold database syncs nothing, by design.
- **Failures are isolated per integration.** An unreachable ERP or an
  undecryptable credential is recorded on that integration's `SyncState` and the
  run continues; the process exits non-zero if any integration failed.
- **Each integration syncs from its own watermark** (`SyncState.last_invoice_date`).
  `--since` overrides it for a backfill; a failed run never advances it.
- **A field a human verified is never overwritten** — see Invoice corrections.
  The ERP restates everything else exactly as before.
- CLI: `--integration-id` (re-run one; it only *filters* the discovered set and
  can never create anything), `--since`, and `--hard-reset` (let the ERP win over
  verified fields; opt-in, never implied by another flag, every overwrite audited
  as actor `system`, human-added lines untouched). There is no `--reset` —
  dropping the schema would delete the integrations that define the work list.
- The runner needs `WEB_API_CREDENTIAL_ENC_KEY` whenever an integration has
  stored credentials, since it decrypts them.

## Tenant scope: active vs. reachable

`TenantScope` carries **two** company sets, and the distinction is load-bearing:

- **`company_ids`** — every company in the org, active or not. The
  **authorization** set: what the caller may reach at all. A deactivated company
  is still theirs, so its detail must load and it must be reactivatable. Never
  narrow this.
- **`active_company_ids`** — the active subset. The **listing** set.
  `resolve_company_ids(scope, None)` returns it, so an unfiltered "all
  companies" view — `/erp-entries`, `/erp-entries/vouchers`, `/invoices`,
  `/invoice-lines`, `/vendors` and every `/reports/*` — covers active companies
  only.

The reason is that `GET /companies` defaults to active, so a client's company
picker offers only those: rows from a deactivated company appearing under "all"
could not be filtered out by any request the client is able to make.
**Asking for a company by id still works**, active or not — history is retained
(companies are soft-deactivated, never deleted) and an explicit request for it is
deliberate, exactly as `?include_inactive` reaches them in the company list.

## ERP connectors

- **`ErpConnector`** (`connectors/base.py`) is the contract; `connectors/http.py`
  carries the plumbing every HTTP connector shares — client, status→exception
  mapping, bounded retry — behind two seams: **`_auth_headers()`, evaluated per
  request** (so a connector whose token expires refreshes there, with nothing
  above it changing), and a declared **paginator** (`connectors/pagination.py`:
  page-number, skip-pages, OData next-link). 429 raises `ErpRateLimitError`,
  carrying `retry_after`.
- A connector may declare **brand metadata** — `brand_slug`, `description`,
  `docs_url` — which `GET /erp-types` projects. That is the *only* place a
  connector's identity is declared: the frontend renders its picker from the
  catalog and knows no connector by name, so registering one is the whole of the
  work needed for it to appear, with a lettered fallback tile when we have no
  artwork (`frontend/src/assets/erp/`, `erp-brand-mark.tsx`).
- **Billy** (`connectors/billy.py`, `erp_type = "billy"`) is the first real ERP.
  Billy API v2, authenticated with a customer's revocable `X-Access-Token`
  (stored encrypted like any credential — **never** an env var); the
  organization is discovered from the token. Its ledger maps
  transaction→voucher, postings→entries, originating bill→invoice scan.
  Four behaviours **contradict Billy's own documentation** and are load-bearing:
  1. The originator is a `"kind:id"` string in `originatorReference`; the
     documented `originatorType` field is null on every row.
  2. `/transactions` accepts date filters and **ignores** them, so `since` is an
     early stop on an `entryDate DESC` scan. (`/postings` and `/bills` do filter
     — the escape hatch if the scan gets slow.)
  3. A document's `downloadUrl` is on S3 and **accepts** the access token, so the
     credential is withheld by an explicit host check; nothing would otherwise
     fail to reveal it being sent to AWS.
  4. Voided transactions come in pairs (`isVoided` original + `isVoid`
     reversal) and **both** are skipped — they net to zero, and counting them
     would present one bill under two vouchers and duplicate the invoice.
  Postings name their account by `accountId`, so the connector maps it through
  the chart; a posting on an unknown account is dropped, not stored blank. Bills
  carry `contactName: null`, so the supplier's name comes from the contact book.
  A bill's **scan is not on the bill**: it hangs off an org-wide `/attachments`
  listing keyed by an `ownerReference` of `"bill:<id>"`, with no per-owner
  filter — so the connector fetches that listing **once** and indexes it, rather
  than once per invoice. `_map_bill` records the resulting `file_ref`, which is
  what makes the sync write a `File` row; without it `has_document` is false and
  `GET /invoices/{id}/document` 404s on a document Billy would have served. The
  attachment names no file, so the name costs one `/files/{id}` lookup per
  invoice — memoised and shared with the document route, which needs the same
  record for the download URL and the media type. Worth it: a good share of
  Billy attachments are phone photos of a receipt, and the runner's `scan.pdf`
  placeholder would be an outright lie about what the customer downloads.
  Tests run against scrubbed captures in `tests/fixtures/billy/` and never touch
  the network; `scripts/billy_fixtures.py` re-captures them and is opt-in.
- Connecting Billy needs `WEB_API_CREDENTIAL_ENC_KEY` set (unlike the Debug ERP,
  whose fields all have defaults) and outbound access to
  `api.billysbilling.com` plus the S3 host its documents live on.

## Model Hosting

- Local vLLM at `http://localhost:8000/v1`, model `google/gemma-4-E4B-it`
  (CrewAI: `hosted_vllm/google/gemma-4-E4B-it`). Configured via `.env`.

## Layout

```text
src/
├── web_api/                  BUSINESS DOMAIN + customer API
│   ├── config.py             domain config: DATABASE_URL + Clerk settings
│   ├── app.py                FastAPI app factory (uvicorn web_api.app:app)
│   ├── auth.py               Clerk JWT verification + JWKS cache
│   ├── deps.py               auth dependency chain + JIT provisioning + tenant scope
│   ├── schemas.py            Pydantic response models
│   ├── audit.py              generic AuditLog helpers (diff + append)
│   ├── documents.py          where an invoice's scan lives (route + AI stage share it)
│   ├── rollup.py             Invoice.status rollup from its lines
│   ├── verified.py           which fields a human settled (sync reads it)
│   ├── reconcile.py          do the lines add up? (API + AI stage share it)
│   ├── spend_trees/          org-owned taxonomies: default template, the only
│   │                         SpendCategory writer, CSV import, reassignment
│   ├── fx/                   historical FX: rate provider + cache, convert,
│   │                         recompute, backfill CLI
│   ├── routers/              companies, invoices, invoice-lines (verify + audit),
│   │                         spend-trees
│   ├── connectors/           ERP connector interface, shared HTTP base,
│   │                         pagination strategies, Billy + Debug ERP
│   ├── dashboard/app.py      Streamlit dashboard (stub)
│   └── db/
│       ├── models/           SQLModel ORM (one file per entity)
│       ├── session.py        engine + session helpers
│       └── migrations/       Alembic
│
└── ai_api/                   AI WORKFLOWS (imports domain from web_api)
    ├── config.py             AI config: LLM factory + vLLM + Qdrant + paths
    ├── models.py             Pydantic schemas (invoice extraction, categorization)
    ├── flow.py               InvoiceFlow (PDF pipeline)
    ├── agents.py             CrewAI agent factories
    ├── grounding.py          categorization guardrail
    ├── web_context.py        buyer + product web context
    ├── ledger.py             CSV output (PDF pipeline)
    ├── pdf_loader.py         PDF text extraction
    ├── parsing.py            LLM JSON repair
    ├── rag/indexer.py        Qdrant vector store (CoA CSV + SpendTree nodes)
    ├── synthdata/            synthetic invoice generator
    ├── persistence/          ai_api-owned store: line_ground_truth (synthetic gt_*)
    ├── sync/runner.py        pipeline orchestrator (discover→connect→fetch→persist→categorize)
    ├── sync/categorizer.py   deterministic keyword categorizer over the company's
    │                         assigned spend tree (stub for Qdrant+LLM)
    ├── documents/            document→invoice lines stage: runner (discover→claim→
    │                         fetch→extract→reconcile→replace), extractor, reconcile
    ├── aggregation/engine.py SQL rollups (stub)
    ├── redundancy/detector.py vendor overlap detection (stub)
    └── procurement_agent/recommender.py  savings suggestions (stub)

mock_erp/                     standalone mock ERP API server (unchanged)
```
