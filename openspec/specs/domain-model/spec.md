# Domain Model Specification

## Purpose

Define the core domain entities for the ERP Procurement Agent. The model supports multi-tenant organizations (bookkeeping firms managing multiple clients), each company having its own spend tree, ERP connections, and users with role-based access.

## Entities

### Organization

A customer account. Can be a business itself or a bookkeeping/virtual-CFO firm managing multiple client companies.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| name | text | |
| created_at | timestamptz | |

### User

A person who can log in. Belongs to an Organization. Has a role that defines their access level across all companies in that org (for MVP — per-company roles later).

Roles:
- `admin` — full access: manage integrations, trigger syncs, manage users
- `member` — view data, dismiss recommendations, export reports
- `viewer` — read-only dashboard access

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | FK → organizations |
| email | text | Unique per org |
| name | text | |
| role | text | "admin" | "member" | "viewer" |
| created_at | timestamptz | |

### Company

A legal entity whose spend is being analyzed. Belongs to an Organization. Has its own spend tree, ERP integrations, vendors, invoices, and transactions.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | FK → organizations |
| name | text | Legal entity name |
| country_code | text | ISO 3166-1 alpha-2, nullable |
| vat_number | text | Nullable |
| created_at | timestamptz | |

### SpendCategory (Spend Tree Node)

One node in a company's spend tree (table `spend_categories`). Distinct from
`ErpAccount` (the ERP's native chart of accounts); the categorizer bridges
`ErpAccount` → `SpendCategory`. `level_1` (Direct/Indirect) is now **stored** on
the node (nullable until classified).

Tree is 2-4 labelled levels:
- level_1: Direct/Indirect (stored, nullable)
- level_2: always present (top-level category, e.g. "Technology")
- level_3: optional (subcategory, e.g. "Cloud Infrastructure")
- level_4: optional (deepest tier)
- leaf: account_code + account_name

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| company_id | UUID | FK → companies |
| account_code | text | Leaf code, e.g. "6010" |
| account_name | text | Leaf name, e.g. "Cloud Hosting & Infrastructure" |
| level_1 | text | Direct/Indirect, nullable until classified |
| level_2 | text | Always present |
| level_3 | text | Nullable (omitted for 2-level trees) |
| level_4 | text | Nullable (deepest tier) |
| description | text | For embedding/retrieval, nullable |

Spend tree is uploaded as CSV or pulled from ERP. Stored in Qdrant for retrieval.
When a company updates their tree, old transactions keep their original categories.
Re-categorization requires an explicit manual trigger.

### File

An uploaded file associated with a Company. Tracks uploads like spend tree CSVs,
invoice PDFs, or exports.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| company_id | UUID | FK → companies |
| uploaded_by | UUID | FK → users, nullable |
| filename | text | Original filename |
| file_type | text | "spend_tree_csv" | "invoice_pdf" | "export" | "synthetic_bundle" |
| storage_path | text | Path on disk or S3 key |
| file_size | integer | Bytes |
| status | text | "uploaded" | "processing" | "processed" | "failed" |
| created_at | timestamptz | |

### ErpIntegration

A connection between a Company and an ERP system.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| company_id | UUID | FK → companies |
| erp_type | text | "business_central" | "e_conomic" | "visma_net" | "dinero" | "ifs_cloud" |
| label | text | Human label, e.g. "Main BC instance" |
| connected_at | timestamptz | When first connected |
| disconnected_at | timestamptz | Null if active |
| created_at | timestamptz | |

Credentials stored separately (encrypted, not in this table). Sync state per integration in SyncState.

### ErpAccount

A native chart-of-accounts node from an ERP system. Every ERP has its own set of accounts (e.g. e-conomic account "6000" = Purchases, Business Central account "6010" = Cloud Hosting). This is the ERP's native classification — distinct from the Company's spend tree (Account), which is the desired target categorization.

The categorizer bridges ErpAccount → Account: it takes ERP entries referencing native accounts and maps them to the spend tree.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| erp_integration_id | UUID | FK → erp_integrations |
| erp_account_code | text | Native account code in the ERP, e.g. "6000" |
| erp_account_name | text | Native account name |
| erp_account_type | text | "asset" | "liability" | "equity" | "income" | "expense" |
| parent_code | text | Parent account code for hierarchy, nullable |
| is_active | boolean | Whether the account is active in the ERP |
| raw_json | jsonb | Original ERP account record |
| created_at | timestamptz | |

### Vendor

A supplier. Belongs to a Company. Referenced by invoices and invoice lines.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| company_id | UUID | FK → companies |
| erp_id | text | Native vendor ID in source ERP, nullable |
| name | text | |
| country_code | text | Nullable |
| vat_number | text | Nullable |
| raw_json | jsonb | Original ERP vendor record |
| created_at | timestamptz | |

### Invoice

An invoice header from an ERP system (or synthetic data). Groups line items together. Has a processing status that tracks its journey through the pipeline.

Statuses:
- `pending` — imported from ERP, not yet processed
- `categorizing` — actively being categorized
- `completed` — all lines categorized
- `failed` — processing error

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| company_id | UUID | FK → companies |
| erp_integration_id | UUID | FK → erp_integrations, nullable |
| vendor_id | UUID | FK → vendors, nullable |
| erp_id | text | Native invoice ID in source ERP, nullable |
| invoice_number | text | |
| invoice_date | date | |
| currency | text | ISO 4217 |
| total | numeric(14,2) | Gross total |
| tax | numeric(14,2) | Nullable |
| status | text | "pending" | "categorizing" | "completed" | "failed" |
| error_message | text | Nullable |
| raw_json | jsonb | Original ERP invoice JSON |
| created_at | timestamptz | |

### InvoiceLine

A single line item from an invoice. This is the SQL model for line items — it carries both the raw ERP line data AND the categorization result. Before categorization, the categorization fields are null.

Statuses:
- `pending` — imported from ERP, awaiting categorization
- `categorized` — successfully categorized (categorization fields populated)
- `failed` — categorization error

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| company_id | UUID | FK → companies |
| invoice_id | UUID | FK → invoices |
| vendor_id | UUID | FK → vendors (denormalized for query perf) |
| erp_integration_id | UUID | FK → erp_integrations, nullable |
| line_erp_id | text | Native line ID in source ERP, nullable |
| description | text | Line item description from source |
| quantity | numeric(12,4) | Nullable |
| unit_price | numeric(12,4) | Nullable |
| amount | numeric(14,2) | Net line amount |
| native_account_code | text | ERP's own account code for this line, nullable |
| status | text | "pending" | "categorized" | "failed" |
| error_message | text | Categorization error details, nullable |
| level1 | text | "Direct" | "Indirect", nullable until categorized |
| level2 | text | From spend tree, nullable until categorized |
| level3 | text | Nullable |
| account_code | text | Chosen leaf account code from spend tree |
| account_name | text | Chosen leaf account name |
| confidence | numeric(4,3) | 0..1, nullable until categorized |
| rationale | text | Categorizer justification, nullable |
| gt_level1 | text | Ground truth (synthetic only) |
| gt_level2 | text | Ground truth (synthetic only) |
| gt_level3 | text | Ground truth (synthetic only) |
| gt_account_code | text | Ground truth (synthetic only) |
| raw_json | jsonb | Original ERP line data |
| created_at | timestamptz | |

`vendor_id` and `erp_integration_id` are denormalized for efficient queries (spend by vendor without joining through Invoice).

### ErpEntry

A raw financial entry from an ERP system. In double-entry accounting, every transaction (purchase invoice, journal entry, payment, credit note) generates one or more entries — each debiting one account and crediting another.

ErpEntry is the universal atomic financial record. Invoice + InvoiceLine is a higher-level view specific to purchase invoices. ErpEntry captures everything, including non-purchase transactions (adjustments, payments, accruals).

Entries are never categorized. The categorizer works on `InvoiceLine`; an entry's spend category, when it has one, is read through the invoice line it was posted from.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| company_id | UUID | FK → companies |
| erp_integration_id | UUID | FK → erp_integrations |
| erp_account_id | UUID | FK → erp_accounts (the native ERP account) |
| entry_type | text | Source document type: "purchase_invoice" | "journal_entry" | "payment" | "credit_note" |
| source_invoice_id | UUID | FK → invoices, nullable (if this entry came from a purchase invoice) |
| entry_date | date | |
| description | text | |
| debit_amount | numeric(14,2) | |
| credit_amount | numeric(14,2) | |
| currency | text | ISO 4217 |
| erp_entry_id | text | Native entry ID in the ERP |
| status | text | "pending" | "categorized" | "failed" |
| raw_json | jsonb | Original ERP entry data |
| created_at | timestamptz | |

Entries carry **no** categorization or ground-truth columns — see "ErpEntry
stores no categorization fields".

### Recommendation

A savings suggestion produced by the procurement agent.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| company_id | UUID | FK → companies |
| rec_type | text | "consolidation" | "alternative_search" | "bulk_signal" |
| category_level2 | text | |
| category_level3 | text | Nullable |
| current_vendor_id | UUID | FK → vendors |
| current_vendor_name | text | Denormalized for display |
| annual_spend | numeric(14,2) | |
| alternative_name | text | Nullable if consolidation-only |
| estimated_savings | numeric(14,2) | |
| savings_pct | numeric(5,2) | 0..100 |
| confidence | numeric(4,3) | 0..1 |
| source | text | "vendor_overlap" | "web_search" | "spend_tier" |
| rationale | text | |
| dismissed | boolean | Default false |
| gt_savings | numeric(14,2) | Ground truth (synthetic only) |
| created_at | timestamptz | |

### SyncState

Sync watermark per ERP integration.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| erp_integration_id | UUID | FK → erp_integrations |
| last_sync_at | timestamptz | |
| last_invoice_date | date | Watermark for incremental sync |
| status | text | "idle" | "syncing" | "error" |
| error_message | text | |
| created_at | timestamptz | |

## Schema Diagram

```
Organization 1──N User
Organization 1──N Company 1──N SpendCategory (spend tree)
                          1──N File
                          1──N ErpIntegration 1──1 SyncState
                                           1──N ErpAccount
                                           1──N ErpEntry
                          1──N Vendor
                          1──N Invoice 1──N InvoiceLine
                          1──N ErpEntry (via source_invoice_id)
                          1──N Recommendation
```

## Key Rules

1. `level_1` (Direct/Indirect) is stored on `SpendCategory` (nullable until classified); the categorizer also infers Direct/Indirect per invoice line for the applied result.
2. Spend tree is 2-4 levels. Minimum: L2 only. Maximum: L2 + L3 + leaf.
3. ERP credentials stored encrypted, not in this schema.
4. Ground truth columns (`gt_*`) are NULL for real data, populated only for synthetic.
5. All queries scoped by `company_id`.
6. Sync is pull-based with date watermark per integration.
7. Old invoice lines keep their categories when spend tree changes. Re-categorization is manual trigger.
8. `vendor_id` and `erp_integration_id` on InvoiceLine are denormalized for query performance.
9. Every Invoice and InvoiceLine has a processing status (`pending` → `categorizing`/`categorized` → `completed` or `failed`).
## Requirements
### Requirement: External identity linkage for Organization and User

The domain model SHALL allow `Organization` and `User` records to be linked to an external identity provider (Clerk). `Organization` SHALL have a nullable, unique `clerk_org_id`, and `User` SHALL have a nullable, unique `clerk_user_id`. These fields carry the provider's principal identifiers so authenticated requests can be mapped to local records. They are NULL for records not backed by an external provider (e.g. synthetic/demo tenants), and MUST be unique when present so a Clerk principal maps to exactly one local record.

#### Scenario: Clerk organization maps to one Organization

- **WHEN** an authenticated request carries a `clerk_org_id`
- **THEN** it resolves to at most one `Organization` (the row whose `clerk_org_id` matches), or triggers creation of one if none exists

#### Scenario: Clerk user maps to one User

- **WHEN** an authenticated request carries a `clerk_user_id`
- **THEN** it resolves to at most one `User`, scoped to the organization identified by the request's `clerk_org_id`

#### Scenario: Synthetic tenants have no external identity

- **WHEN** a demo/synthetic `Organization` or `User` is created by the sync runner
- **THEN** its `clerk_org_id` / `clerk_user_id` is NULL and the record remains valid

### Requirement: Organization profile and lifecycle

The `Organization` entity SHALL be a first-class domain record beyond its Clerk mirror. It SHALL have a `slug` (nullable, unique when present — a human-readable handle, typically the Clerk org slug) and a `status` (`active` or `suspended`, default `active`). These are managed via the organization profile endpoints and provisioned from Clerk where available.

#### Scenario: New organization defaults to active

- **WHEN** an `Organization` is provisioned
- **THEN** its `status` is `active` and its `slug` may be null until set

#### Scenario: Slug is unique when present

- **WHEN** two organizations would have the same non-null `slug`
- **THEN** the second write is rejected (uniqueness violation)

### Requirement: Company activation state

The `Company` entity SHALL carry activation state: `is_active` (boolean, default `true`) and `deactivated_at` (timestamp, nullable). Deactivation is a soft state change that preserves the company and its financial data (invoices, invoice lines); companies are never hard-deleted through the API.

#### Scenario: Company defaults to active

- **WHEN** a `Company` is created
- **THEN** `is_active` is `true` and `deactivated_at` is null

#### Scenario: Deactivation preserves related data

- **WHEN** a company is deactivated
- **THEN** its `Invoice` and `InvoiceLine` rows are unchanged and still reference the company

### Requirement: Company carries a base currency

`Company` SHALL carry a non-null `base_currency` holding an ISO 4217 alphabetic
code. It is a customer setting, not ERP metadata: no connector, sync, or
refresh SHALL overwrite it.

#### Scenario: Base currency is required on the row

- **WHEN** a `Company` is persisted
- **THEN** it has a `base_currency`, and a company without one cannot be stored

#### Scenario: A sync never rewrites it

- **WHEN** an ERP sync or account refresh runs for the company
- **THEN** `base_currency` is left exactly as the customer set it

### Requirement: Platform and organization roles

`User` SHALL carry a platform-level `is_system_admin` boolean (default `false`) in addition to its organization `role`. The organization `role` set SHALL be `admin`, `moderator`, `member`, or `viewer`. `is_system_admin` grants cross-organization management privileges independent of the org role.

#### Scenario: Default user is not a system admin

- **WHEN** a `User` is provisioned without a system-admin claim
- **THEN** `is_system_admin` is `false`

#### Scenario: Moderator is a valid organization role

- **WHEN** a user is assigned the `moderator` role
- **THEN** the value is accepted and treated as a write-capable organization role

### Requirement: Webhook event record

The domain SHALL include a `WebhookEvent` entity that records inbound provider webhooks for idempotency and audit. It SHALL carry a `provider` (e.g. `clerk`), a provider `event_id` that is unique (the idempotency key), an `event_type`, the raw `payload` (JSON), a `received_at` timestamp, a `processed` flag, and an optional `error`. A given `(provider, event_id)` SHALL appear at most once.

#### Scenario: Duplicate event id is rejected

- **WHEN** two webhook deliveries share the same provider `event_id`
- **THEN** only the first is stored/applied; the second is recognized as already processed

### Requirement: Organization suspension lifecycle

The `Organization` entity SHALL support a suspension lifecycle: in addition to `status` (`active` | `suspended`), it SHALL have a nullable `suspended_at` timestamp set when the organization is suspended and cleared when it is reactivated. Suspension is a soft state that retains all child data (companies, invoices, lines).

#### Scenario: Suspension sets the timestamp

- **WHEN** an organization is suspended
- **THEN** `status` is `suspended` and `suspended_at` is set, while its companies and invoices remain

#### Scenario: Reactivation clears the timestamp

- **WHEN** a suspended organization is reactivated
- **THEN** `status` is `active` and `suspended_at` is null

### Requirement: User access revocation

Revoking a user (membership removed or user deleted in Clerk) SHALL remove that user's ability to access the organization via the API, without corrupting records that reference the user. Nullable references to the user (e.g. `File.uploaded_by`) SHALL be cleared rather than left dangling.

#### Scenario: Revoked user cannot authenticate into the org

- **WHEN** a user's membership is revoked
- **THEN** subsequent requests by that user are not provisioned into the organization

#### Scenario: References remain valid after revocation

- **WHEN** a user who uploaded a file is revoked
- **THEN** the file record remains valid with its `uploaded_by` cleared (not pointing to a missing user)

### Requirement: SpendTree entity

The domain SHALL carry a `SpendTree` entity, stored in `spend_trees`, holding `id`, `organization_id` (FK → organizations), `name`, `max_depth` (3 or 4), `source` (`default_template` | `custom`), nullable `template_version`, `archived_at`, and `created_at`. The Organization relationship SHALL be exposed as `Organization.spend_trees`.

`Company` SHALL carry a nullable `spend_tree_id` (FK → spend_trees) naming the tree it categorizes against, exposed as `Company.spend_tree`. The referenced tree MUST belong to the company's own organization.

#### Scenario: A tree belongs to an organization, not a company

- **WHEN** an organization's trees are loaded
- **THEN** each is a `SpendTree` row with that `organization_id`, reachable via `Organization.spend_trees`, and companies reference it rather than owning it

#### Scenario: Companies point at a tree

- **WHEN** a company is assigned a tree
- **THEN** `Company.spend_tree_id` holds that tree's id and `Company.spend_tree` resolves to it

### Requirement: Spend-tree nodes are modeled as SpendCategory

The spend-tree node SHALL be the `SpendCategory` entity, stored in the `spend_categories` table, replacing the former `Account`/`accounts` naming which collided with the ERP's native `ErpAccount`.

- A `SpendCategory` SHALL belong to a `SpendTree` (`spend_tree_id` FK → spend_trees), **not** to a Company. The former `company_id` column SHALL be removed; a company reaches its nodes through `Company.spend_tree`.
- The tree relationship SHALL be exposed as `SpendTree.categories`.
- A node SHALL carry a nullable `parent_id` (FK → spend_categories, null at depth 1), a `depth` of 1–4, its own `name`, a `sort_order`, an optional `code`, and an optional `description`.
- `name`, `code`, and `description` SHALL be the leaf identity and embedding text used for retrieval and categorization.
- Sibling `name` values SHALL be unique under one parent within a tree, and `code` SHALL be unique within a tree when present.

#### Scenario: Spend categories are scoped to a tree

- **WHEN** a tree's nodes are loaded
- **THEN** each node is a `SpendCategory` row with that `spend_tree_id`, reachable via `SpendTree.categories`, and no node carries a `company_id`

#### Scenario: A company reaches its nodes through its tree

- **WHEN** a company's spend tree is needed
- **THEN** it is resolved as `Company.spend_tree.categories`, and two companies assigned the same tree see the same node rows

#### Scenario: Parentage is explicit

- **WHEN** a node below the top level is loaded
- **THEN** its `parent_id` names its parent node and its `depth` is one greater than that parent's

### Requirement: SpendCategory stores four labelled levels including Direct/Indirect

`SpendCategory` SHALL store an explicit level path `level_1`, `level_2`, `level_3`, `level_4`, where `level_1` holds the Direct/Indirect classification that was previously inferred and never persisted.

- The `level_*` columns SHALL be the **materialized path** of the node — the `name` of each ancestor and of the node itself — derived from `parent_id` and rewritten in the same transaction whenever a node is renamed or reparented. They are a read optimization for categorization results, never an independent source of truth about structure.
- `level_n` SHALL be set exactly when the node's `depth` is at least `n`, and null otherwise. Every `level_*` column is therefore nullable, including `level_2`, which the pre-tree model required: `Direct` and `Indirect` are real depth-1 rows — the tier a reviewer picks first — and a depth-1 node's path is its `level_1` alone.
- `level_1` SHALL hold the Direct/Indirect value on the default template's trees and SHALL be stored on the node. This supersedes the prior rule that L1 is never stored, and the prior rule that `level_2` is required.
- `level_4` SHALL be populated only on a tree whose `max_depth` is 4.

#### Scenario: Direct/Indirect is stored on the node

- **WHEN** a spend category is classified as Direct or Indirect
- **THEN** its `level_1` field holds that value

#### Scenario: A depth-1 node has only its own level

- **WHEN** the node `Indirect` is loaded from the default template's tree
- **THEN** its `depth` is 1, its `level_1` is `Indirect`, and its `level_2`, `level_3` and `level_4` are null

#### Scenario: Optional deeper levels

- **WHEN** a tree uses only two tiers
- **THEN** a leaf has `level_1` and `level_2` set with `level_3` / `level_4` null, and remains valid

#### Scenario: The path follows the structure

- **WHEN** a node's parent is renamed
- **THEN** that node's materialized `level_*` path is rewritten to match, in the same transaction as the rename

### Requirement: Invoice carries the internal file reference and no voucher

An `Invoice` SHALL record the internal File reference for the scanned document and SHALL NOT store the ERP voucher id (an `Invoice` is an invoice scan: the digitized supplier document and its line items; the voucher belongs to `ErpEntry`).

- `Invoice` SHALL have a nullable `file_id` (FK → `files`) — the reference into
  the internal File domain for the stored scan document. It is NULL when no scan
  file is available (e.g. purely synthetic data with no rendered document).
- `Invoice` SHALL NOT have a `voucher_id` column; the voucher is recorded on
  `ErpEntry`, and the entry→invoice association is resolved at ingest, not stored
  on the invoice.
- `file_id` is distinct from `erp_id`/`invoice_number`; those fields keep the
  native invoice number and SHALL NOT be overloaded to carry the voucher.

#### Scenario: Invoice records its scan file, not a voucher

- **WHEN** an invoice scan is imported for a voucher that has an attached document
- **THEN** the persisted `Invoice` has `file_id` set to the internal `files` row
  for the scan and exposes no voucher field

#### Scenario: Missing scan document leaves file reference null

- **WHEN** an invoice scan is imported for a voucher that has no attached
  document file
- **THEN** the persisted `Invoice` has `file_id` NULL and import still succeeds

### Requirement: Entries resolve to at most one invoice scan via the voucher

`ErpEntry` records SHALL relate to invoice scans as **many entries → one
invoice**, resolved through the shared voucher. A single voucher may post several
entries (net, VAT, rounding, split accounts); all of them SHALL point at the one
`Invoice` scan for that voucher.

- `ErpEntry` SHALL have a `voucher_id` (text) column recording the voucher of the
  posting it belongs to.
- When an invoice scan exists for an entry's voucher, the entry's
  `source_invoice_id` SHALL be set to that invoice. The match is resolved from the
  voucher at ingest; the invoice itself does not store the voucher.
- An entry whose voucher has no invoice scan (journal entry, payment, credit note
  with no scanned document) SHALL be persisted with `source_invoice_id` NULL.
- No `Invoice` field is derived by summing entries in this change; the invoice
  scan totals come from the scan payload, and entries are stored as raw financial
  context alongside it.

#### Scenario: Multiple entries link to one invoice scan

- **WHEN** a voucher for a purchase invoice posts three entries (net, VAT,
  rounding) and its invoice scan is imported
- **THEN** all three `ErpEntry` rows share the same `voucher_id` and have
  `source_invoice_id` pointing at the same `Invoice`, which stores no voucher

#### Scenario: Non-invoice entry has no source invoice

- **WHEN** an entry belongs to a voucher that has no invoice scan (e.g. a payment)
- **THEN** the `ErpEntry` row is persisted with `source_invoice_id` NULL

### Requirement: Categorization scope remains invoices and invoice lines

AI categorization SHALL continue to operate only on `Invoice` and `InvoiceLine`.
Adding entry ingestion SHALL NOT cause `ErpEntry` rows to be categorized by the
sync pipeline; entries are persisted as raw financial context only.

#### Scenario: Entries are not categorized on import

- **WHEN** the sync pipeline persists entries and then runs categorization
- **THEN** only `InvoiceLine` rows are categorized, and `ErpEntry` rows retain
  their default `status` with categorization fields unset

### Requirement: ErpAccount has a sync-selection toggle distinct from ERP active state

`ErpAccount` SHALL carry a `sync_enabled` boolean that WE own, controlling whether the sync pulls entries for that account, and it SHALL be distinct from `is_active` (which mirrors the ERP's own active/inactive state).

- `sync_enabled` SHALL default to `true` so a first sync behaves as before.
- `sync_enabled` SHALL be preserved across re-syncs — refreshing an account's
  metadata from the ERP MUST NOT reset a user's selection.
- `is_active` SHALL continue to reflect the ERP's active flag and MUST NOT be
  overloaded as the sync toggle.
- `sync_enabled` is scoped per `ErpAccount`, i.e. per `ErpIntegration` per Company.
- Disabling an account SHALL NOT delete entries already persisted for it. The
  history is retained.
- Disabling an account SHALL, however, **hide** its entries from the entry
  listings. An account is enabled when first discovered, so anything pulled
  before a customer narrowed their selection stays in the database; leaving it
  visible contradicts the setting that says the account is not part of their
  spend picture. Hiding rather than deleting is what makes the toggle
  reversible — re-enabling an account brings its history straight back.
- The toggle SHALL govern *listings*, not lookup by id, exactly as the
  excluded-entry-type rule does.

#### Scenario: Disabled account is excluded from entry ingestion

- **WHEN** an `ErpAccount` has `sync_enabled = false`
- **THEN** the sync does not fetch or persist any `ErpEntry` for that account

#### Scenario: Selection survives a re-sync

- **WHEN** an account is toggled `sync_enabled = false` and the ERP accounts are
  fetched again on the next sync
- **THEN** the account's `sync_enabled` stays `false` while its name, type and
  parent metadata are refreshed

#### Scenario: Disabling an account leaves its history intact but unlisted

- **WHEN** an account with already-synced entries is set to `sync_enabled = false`
- **THEN** its existing `ErpEntry` rows remain in the database, future ingestion
  stops, and those rows no longer appear in the entry listings

#### Scenario: Re-enabling an account restores its entries

- **WHEN** a deselected account with retained history is set back to
  `sync_enabled = true`
- **THEN** its existing entries appear in the listings again, with no re-sync

### Requirement: ErpAccount records whether it is with or without VAT

`ErpAccount` SHALL carry a `with_vat` boolean that WE own, recording whether the account is **assumed** to be configured with VAT — seeded from the ERP account when the account is first discovered, and preserved thereafter.

- `with_vat` SHALL be set from the ERP account data when an `ErpAccount` row is
  **created**, since the ERP's value is the best available starting assumption.
- `with_vat` SHALL be **preserved** on every subsequent upsert — neither an
  account refresh nor a re-sync may overwrite it. This applies to every writer of
  `ErpAccount`, not to one code path.
- The value is a customer judgement, not a fact the ERP asserts: some ERPs do not
  report it and the connector defaults it to `false`, which must not be
  re-asserted as truth over a setting the customer has made.
- `with_vat` recomputes no stored amount. It exists so reconciliation can decide
  whether to read invoice lines as including or excluding VAT when comparing a
  predicted total against posted entries — which is what distinguishes a VAT
  difference from a total difference.

#### Scenario: VAT flag is seeded from the ERP account

- **WHEN** an account is discovered for the first time and the ERP reports it as
  with-VAT
- **THEN** the created `ErpAccount` has `with_vat = true`

#### Scenario: Without-VAT account is seeded as such

- **WHEN** an account is discovered for the first time and the ERP reports it as
  without-VAT
- **THEN** the created `ErpAccount` has `with_vat = false`

#### Scenario: A customer's VAT setting survives an account refresh

- **WHEN** a customer sets an account's `with_vat` to the opposite of what the ERP
  reports, and the chart of accounts is then refreshed from the ERP
- **THEN** the account keeps the customer's value while its name, type, parent and
  ERP active state are refreshed

#### Scenario: A customer's VAT setting survives a sync

- **WHEN** a customer sets an account's `with_vat` and the sync pipeline then runs
  and upserts that account
- **THEN** the account keeps the customer's value

### Requirement: ErpCredential stores an integration's connection secrets encrypted

The domain model SHALL include an `ErpCredential` entity holding an `ErpIntegration`'s connection configuration (e.g. base URL, API key) **encrypted at rest**, kept separate from the `ErpIntegration` table.

- `ErpCredential` SHALL reference exactly one `ErpIntegration` (one active
  credential per integration).
- The stored config SHALL be encrypted (not plaintext) and SHALL only be decrypted
  server-side to construct a connector; it SHALL NOT be exposed via any API
  response.
- Fields SHALL include: `id`, `erp_integration_id` (FK → erp_integrations),
  `encrypted_config` (ciphertext), `created_at` (and an update timestamp).

#### Scenario: Credentials persist encrypted, never returned

- **WHEN** an integration is created with credentials
- **THEN** an `ErpCredential` row stores the config as ciphertext, and no API
  response returns the decrypted values

### Requirement: ErpIntegration has a soft-disconnect lifecycle

An `ErpIntegration` SHALL support soft-disconnect via its `disconnected_at` timestamp: a disconnected integration is retained (with its accounts, entries, and sync state) and MAY be reconnected by clearing the timestamp.

- Disconnecting SHALL set `disconnected_at` and MUST NOT delete related
  `ErpAccount`, `ErpEntry`, or `SyncState` rows.
- Reconnecting SHALL clear `disconnected_at`.
- An integration with `disconnected_at` set SHALL be treated as inactive by
  default listings.

#### Scenario: Disconnect retains related data

- **WHEN** an integration is disconnected
- **THEN** `disconnected_at` is set and its `ErpAccount`/`ErpEntry` rows are retained

#### Scenario: Reconnect reactivates

- **WHEN** a disconnected integration is reconnected
- **THEN** `disconnected_at` is null and it appears in default active listings

### Requirement: InvoiceLine carries its categorization result and status

The `InvoiceLine` domain entity SHALL hold its categorization result directly: `level_1`, `level_2`, `level_3`, `level_4`, `account_code`, `account_name`, `confidence`, `rationale`, plus the accepted `spend_category_id` (FK to a node of the company's assigned spend tree, nullable until resolved). Its `status` SHALL use the categorization vocabulary `uncategorized` | `ai_failed` | `ai_categorized` | `verified`. The line SHALL NOT carry synthetic ground-truth (`gt_*`) fields, and there SHALL be no separate domain `LineCategorization` table.

The stored `level_*` values SHALL survive independently of `spend_category_id`: they are the record of what was decided, and they remain readable when the pointer is cleared because the company's tree changed.

#### Scenario: Result fields on the line

- **WHEN** a line is categorized
- **THEN** its `level_*`, `account_code`, `account_name`, `confidence`, and `rationale` are set on the line and its status reflects `ai_categorized` or `verified`

#### Scenario: No ground truth on the domain line

- **WHEN** inspecting `invoice_lines`
- **THEN** there are no `gt_*` columns

#### Scenario: Levels outlive the pointer

- **WHEN** a line's `spend_category_id` is cleared because its node is not in the company's assigned tree
- **THEN** its `level_1`..`level_4` are unchanged and still readable

### Requirement: InvoiceLine records a fourth categorization level

`InvoiceLine` SHALL carry a nullable `level_4` beside `level_1`, `level_2` and `level_3`, so a categorization against a four-level tree has somewhere to record its leaf. `level_4` SHALL be null whenever the assigned tree is three levels deep, which is the ordinary case, and SHALL NEVER be defaulted or inferred.

`level_4` SHALL be part of the line's auditable categorization fields, so a correction to it is diffed and recorded like any other level.

#### Scenario: A four-level categorization is stored whole

- **WHEN** a line is categorized against a node at depth 4
- **THEN** the line's `level_1`..`level_4` hold that node's full path

#### Scenario: Three-level trees leave it null

- **WHEN** a line is categorized against a three-level tree
- **THEN** the line's `level_4` is null

#### Scenario: Correcting level_4 is audited

- **WHEN** a manager verifies a line while changing its `level_4`
- **THEN** the audit entry records the `level_4` change alongside any other changed field

### Requirement: Invoice status is a categorization rollup

`Invoice.status` SHALL reflect the aggregate categorization state of its lines rather than an independent value: `uncategorized` when no line is categorized, a categorized/in-progress state once lines are AI-categorized, and `verified` when every line is `verified`.

#### Scenario: Rollup reflects line states

- **WHEN** all of an invoice's lines are `verified`
- **THEN** the invoice's status is `verified`

### Requirement: AuditLog entity

The domain SHALL include an `AuditLog` entity recording changes over time: `id`, `entity_type` (`invoice` | `invoice_line`), `entity_id`, `action`, `actor` (user id or `system`), `changes` (JSON of per-field old→new values), and `created_at`. It is append-only and scoped to the owning organization through the referenced entity.

#### Scenario: Audit row shape

- **WHEN** a categorization or verification occurs
- **THEN** an `AuditLog` row captures the entity, action, actor, and field changes with a timestamp

### Requirement: ErpEntry records the accounting date

`ErpEntry` SHALL record the ledger posting date in a column named
`accounting_date` (nullable `date`). This is the entry's accounting/posting date
and the axis used for period-based reporting. The entry SHALL NOT expose an
ambiguous `entry_date`.

#### Scenario: Posting date is named accounting_date

- **WHEN** an entry is persisted from ERP data
- **THEN** its posting date is stored in `accounting_date`, and no `entry_date`
  column exists on `erp_entries`

#### Scenario: Reporting aggregates on the accounting date

- **WHEN** entries are aggregated over a date range
- **THEN** the range is applied to `accounting_date`

### Requirement: ErpEntry integration is derived through its account

`ErpEntry` SHALL NOT store a direct `erp_integration_id`. An entry's ERP
integration SHALL be reached through its account
(`ErpEntry.erp_account_id → ErpAccount.erp_integration_id`); the entry retains
`company_id` for tenant scope. Scoping an integration's entries SHALL join
through `ErpAccount`.

#### Scenario: No direct integration column

- **WHEN** inspecting `erp_entries`
- **THEN** there is no `erp_integration_id` column, and the integration is
  resolved via the entry's account

#### Scenario: Entries scoped to an integration via the account

- **WHEN** the sync selects the entries belonging to a given integration
- **THEN** it joins `ErpEntry` to `ErpAccount` and filters
  `ErpAccount.erp_integration_id`, and re-syncing the same source upserts the
  same entry rows (idempotent)

### Requirement: ErpEntry stores no categorization fields

`ErpEntry` SHALL NOT store any categorization output or ground truth. Entries are raw financial context and are never categorized, so the table SHALL carry no `level_1/2/3`, `account_code`, `account_name`, `confidence`, `rationale`, or `gt_*` columns.

- The native account is referenced via `erp_account_id`; it SHALL NOT be
  duplicated as categorization `account_code`/`account_name` on the entry.
- Categorization belongs to the invoice line, and an entry that came from a line
  only *reads through* that link — no per-entry categorization record exists.

#### Scenario: Persisted entry carries no categorization columns

- **WHEN** the sync pipeline persists `ErpEntry` rows
- **THEN** each entry exposes its raw financial fields, `erp_account_id`, and
  `status`, and the table has no categorization or ground-truth columns

### Requirement: Entries link to the invoice line they were posted from

`ErpEntry` SHALL carry a nullable `source_invoice_line_id` foreign key to
`InvoiceLine`, relating the two as **many entries → one line**. A single invoice
line may be posted across several accounts, so the link points from the posting
to the line and never the other way; `InvoiceLine` gains no reference back.

- The column SHALL be nullable, and NULL SHALL be the ordinary case rather than
  a defect. Input VAT, the accounts-payable counterparty, journal entries and
  payments are properties of a whole voucher and have no line behind them.
- The link SHALL be set only when the connector states which line a posting came
  from (`ErpEntryData.source_line_erp_id`). It SHALL NOT be inferred by matching
  on amount, account or description — an ERP that nets several lines into one
  posting would make any such guess silently wrong.
- The linked line SHALL be resolved by *deriving* its id from the same
  `(invoice, line_erp_id)` pair the invoice persistence uses, so the two agree by
  construction rather than by resemblance.
- A posting naming a line its invoice scan did not deliver SHALL be persisted
  with the link NULL rather than aborting the sync on a dangling key.
- `ErpEntry` SHALL still carry no categorization of its own. This link exists so
  that a posting can be read against the line whose category applies to it; the
  categorization remains the line's.

#### Scenario: A posting is linked to its line

- **WHEN** a connector reports a posting carrying the ERP's line id, and that
  invoice line was imported with the voucher's scan
- **THEN** the `ErpEntry` row's `source_invoice_line_id` points at that
  `InvoiceLine`

#### Scenario: Several postings share one line

- **WHEN** one invoice line is posted as more than one entry
- **THEN** every one of those entries points at the same `InvoiceLine`, and the
  line stores no reference back to them

#### Scenario: A posting with no line behind it

- **WHEN** an input-VAT, payable, or journal-entry posting is persisted
- **THEN** its `source_invoice_line_id` is NULL

#### Scenario: A dangling line reference does not fail the sync

- **WHEN** a connector names a line id that the invoice scan never delivered
- **THEN** the entry is persisted with `source_invoice_line_id` NULL and the sync
  continues

### Requirement: FxRate stores one daily reference rate per currency and date

A `FxRate` entity SHALL store the daily reference rate for one currency on one
date, expressed as units of that currency per 1 EUR, together with the source
that produced it and when it was fetched. `(quote_currency, rate_date)` SHALL be
unique.

- A row SHALL also record the `published_date` the rate was actually published
  for, which differs from `rate_date` when a non-publication date resolved
  backwards to an earlier publication. Caching the resolved rate under the
  requested date keeps that date from being re-requested without passing a
  lookup date off as a publication date.

`FxRate` is reference data, not tenant data: it SHALL carry no
`organization_id` and no `company_id`, and one row SHALL serve every company.

#### Scenario: A rate is stored once per currency and date

- **WHEN** the same currency and date are looked up by two different companies
- **THEN** one `FxRate` row serves both, and no duplicate row is written

#### Scenario: Rates are not tenant-scoped

- **WHEN** an `FxRate` row is inspected
- **THEN** it references no organization or company

### Requirement: Money-bearing rows carry their base-currency conversion

`Invoice`, `InvoiceLine` and `ErpEntry` SHALL each carry, alongside their
as-posted currency and amounts, a nullable `base_currency`, nullable base
amount column(s) mirroring their money columns, a nullable `fx_rate`, and a
nullable `fx_rate_date`.

- `Invoice` SHALL mirror `total` and `tax`.
- `InvoiceLine` SHALL mirror `amount`.
- `ErpEntry` SHALL mirror `debit_amount` and `credit_amount`.
- Base amounts SHALL use the same numeric scale as the columns they mirror;
  `fx_rate` SHALL be stored with enough precision that a stored base amount can
  be re-derived from the original amount and the rate.
- Null base fields SHALL mean "not converted" — never "converted to zero".
- The existing `currency` and amount columns SHALL retain their meaning: the
  value exactly as the ERP posted it.

#### Scenario: An entry carries both figures

- **WHEN** a converted `ErpEntry` is read
- **THEN** it exposes its posted currency and debit/credit amounts, and its base
  currency, base debit/credit amounts, rate, and rate date

#### Scenario: Unconverted means null, not zero

- **WHEN** a row could not be converted
- **THEN** its base amount columns are null, and no consumer reads them as `0`

#### Scenario: The posted amount is never rewritten

- **WHEN** a row is converted or later recomputed
- **THEN** its `currency` and posted amounts are byte-identical to before

### Requirement: InvoiceLine records where it came from

`InvoiceLine` SHALL carry a non-null `origin` of `erp`, `document_ai`, or
`entry_fallback`, recording which source produced the line.

- `erp` — the ERP supplied the line itself (a bill line on the voucher).
- `document_ai` — our AI extracted the line from the invoice's attached document.
- `entry_fallback` — no document extraction was available, so the line stands in
  for one expense posting on the voucher.
- Precedence between sources SHALL be `document_ai` > `erp` > `entry_fallback`.
  The document is the only source that knows what was actually bought; the ERP's
  own lines are its statement of the same voucher; a posting is the last resort.
- `origin` SHALL be a property of the line and SHALL NOT be inferred from its
  values at read time. A stand-in line and an extracted line can carry identical
  descriptions and amounts, and the difference — whether anyone has read the
  document — is exactly what a reader needs to know.
- An invoice SHALL NOT hold lines of more than one origin at a time. Two origins
  describe the same spend twice and its total would be double-counted.
- Existing rows SHALL be backfilled to `erp`, which is what every line written
  before this change was.

#### Scenario: A line states its source

- **WHEN** a line is read back
- **THEN** it carries an `origin` of `erp`, `document_ai` or `entry_fallback`

#### Scenario: A stand-in and an extracted line are distinguishable

- **WHEN** a stand-in line and an extracted line carry the same description and
  amount
- **THEN** they are still told apart by `origin`

#### Scenario: One origin per invoice

- **WHEN** an invoice's lines are listed
- **THEN** every line shares the same `origin`

### Requirement: InvoiceLine records its position on the invoice

`InvoiceLine` SHALL carry a non-null `sequence` recording the position its
source stated it in, and every reader SHALL order an invoice's lines by it.

- A line's `id` is a random UUID, so ordering by it alone presents a document's
  lines in an arbitrary sequence. That was invisible while the Entries page
  listed postings; it is wrong the moment the page lists lines, because an
  invoice reads top to bottom and its lines are no longer interchangeable rows.
- The writers SHALL set it from the order their source gave: the ERP's line
  order, the document's line order, or the posting order for stand-ins.
- `id` SHALL remain the tiebreak, so the order is total and deterministic even
  where two lines share a sequence.
- Existing rows SHALL be backfilled to `0`, which leaves their relative order
  exactly as it was.

#### Scenario: Lines read in the order their source stated them

- **WHEN** a document's three lines are extracted and the invoice is read back
- **THEN** they come back in the document's order, not in id order

#### Scenario: The order is total

- **WHEN** two lines share a `sequence`
- **THEN** they are still returned in a stable order on every request

### Requirement: InvoiceLine records the unit its quantity is counted in

`InvoiceLine` SHALL carry a nullable `unit` — the unit of measure the line's
`quantity` is expressed in (`pcs`, `hours`, `kg`, `months`).

- A bare quantity is ambiguous: `12` against "Consulting" is twelve hours or
  twelve days or twelve engagements, and a spend tool that compares unit prices
  across suppliers cannot compare them without it.
- It SHALL be taken from whichever source stated it, and SHALL be null when none
  did. Null is the ordinary case: an ERP's bill line states an account and an
  amount, not a unit of measure — Billy's carries `quantity` with no unit field
  at all — and a posting has neither. Only the document reliably names one.
- It SHALL NOT be inferred from the description, and no default SHALL be
  substituted. "pcs" assumed over an hourly consulting line is a wrong figure
  presented with confidence.

#### Scenario: An extracted line carries its unit

- **WHEN** a document states "12 hours" on a line and it is extracted
- **THEN** the line's `quantity` is 12 and its `unit` is `hours`

#### Scenario: An ERP line that names no unit stores none

- **WHEN** a Billy bill line with `quantity: 1` and no unit field is synced
- **THEN** the line's `unit` is null rather than a substituted default

#### Scenario: A stand-in line has no unit

- **WHEN** a posting stands in for a line
- **THEN** its `unit` is null

### Requirement: Invoice records the number printed on the document

`Invoice` SHALL carry a nullable `document_invoice_number` — the supplier's
invoice number as read from the attached document — **beside** the as-posted
`invoice_number`, which SHALL NEVER be rewritten by extraction.

- The as-posted value is frequently not an invoice number at all. Billy's
  `suppliersInvoiceNo` is user-entered and often null, and `voucherNo` is blank
  at least as often, so the connector falls back to the **bill id** — an
  internal identifier presented in a field the reader takes for the supplier's
  number. The number printed on the invoice is the one a human reconciles
  against, and only the document has it.
- The two SHALL be stored separately for the same reason `base_total` sits
  beside `total` rather than replacing it: the as-posted column is the evidence,
  and overwriting it would destroy the record of what the ERP actually holds and
  make the two impossible to compare.
- A reader SHALL be shown the document's number in preference to the as-posted
  one, and SHALL be able to see both when they disagree — a disagreement is
  information (the ERP's is wrong, or the scan is of a different invoice), not
  noise to resolve silently.
- Extraction SHALL leave it null rather than guess when the document states no
  number.
- **`document_invoice_number` SHALL be correctable by a human**, and its original
  value SHALL be recoverable from the audit log. It is a value a model read off a
  scan, and a misread digit is exactly the kind of error a reviewer is there to
  fix.
- `invoice_number` SHALL remain the as-posted evidence. Its correctability
  through the API is unchanged by this requirement; what changes is that it is no
  longer the field a reviewer is *presented* with, since the number worth
  reconciling against is the printed one.

#### Scenario: The printed number is stored beside the posted one

- **WHEN** a bill whose `invoice_number` fell back to the bill id is extracted
  and the document reads "2026-0412"
- **THEN** `document_invoice_number` is "2026-0412" and `invoice_number` still
  holds the bill id

#### Scenario: Extraction never rewrites the posted number

- **WHEN** an invoice is extracted
- **THEN** its `invoice_number` is exactly what it was before

#### Scenario: A document that states no number stores none

- **WHEN** the extraction yields no invoice number
- **THEN** `document_invoice_number` is null

#### Scenario: A misread printed number is corrected

- **WHEN** a reviewer corrects `document_invoice_number` from "2026-04I2" to
  "2026-0412"
- **THEN** the stored value is the correction and the audit log holds the
  original

#### Scenario: The posted number stays as the ERP stated it

- **WHEN** a reviewer corrects the printed number on an invoice whose
  `invoice_number` fell back to the bill id
- **THEN** `invoice_number` still holds the bill id, unchanged

### Requirement: Invoice records its document-processing state

`Invoice` SHALL carry `doc_status`, `doc_attempts`, `doc_error` and
`doc_processed_at` describing whether its attached document has been turned into
lines.

- `doc_status` SHALL be one of `not_applicable`, `pending`, `processing`,
  `processed`, `failed`.
- These fields SHALL be distinct from `Invoice.status`, which remains the
  categorization rollup of the invoice's lines. One says whether we have read the
  document; the other says whether the resulting spend has been categorized and
  verified. Conflating them would make an invoice with no scan look uncategorized
  and a categorized invoice look processed.
- Existing rows SHALL be backfilled to `not_applicable` where no file is
  attached and `pending` where one is, so the first stage run picks up the
  backlog without a separate migration step.

#### Scenario: The two statuses are independent

- **WHEN** an invoice's document extraction fails but its stand-in lines are all
  categorized
- **THEN** its `doc_status` is `failed` and its `status` is `categorized`

#### Scenario: Existing invoices with a scan are queued by the migration

- **WHEN** the migration runs over invoices that already carry a `file_id`
- **THEN** those invoices read `pending` and the rest read `not_applicable`

### Requirement: InvoiceLine names what was bought, beside describing it

`InvoiceLine` SHALL carry a nullable `item_name` — the name of the product or
service on the line — **beside** its existing `description`.

The two are different statements and were being made by one field:

- `item_name` is what was bought. It is short, expected on every line, and it is
  the value a redundancy or savings comparison is actually about: "Figma
  Organization seat" is comparable across suppliers in a way that a sentence of
  prose is not.
- `description` is supplementary prose the supplier printed. It is frequently
  absent, and nothing downstream may assume it is present.

Constraints:

- `item_name` SHALL be nullable in the schema. A posting-derived stand-in line
  is built from a ledger memo that is itself frequently null, and a NOT NULL
  column would force the sync to invent a name.
- A reader SHALL be shown `item_name` as the line's primary label, falling back
  to `description` only when `item_name` is null.
- Both SHALL be correctable by a human, and both SHALL be recoverable from the
  audit log after correction.
- Existing rows SHALL be migrated: the stored `description` becomes `item_name`
  and `description` becomes null, because the single field was in practice
  holding the name.

#### Scenario: A line carries both

- **WHEN** a document states the item "Figma Organization seat" and the
  description "Annual plan, 12 seats, billed yearly"
- **THEN** the line's `item_name` is "Figma Organization seat" and its
  `description` is "Annual plan, 12 seats, billed yearly"

#### Scenario: A description-less line is still named

- **WHEN** a document states an item name and no further prose
- **THEN** `item_name` is set and `description` is null

#### Scenario: A stand-in line with no memo names nothing

- **WHEN** a stand-in line is written from a posting whose description is null
- **THEN** `item_name` is null rather than a fabricated value

#### Scenario: Migration moves the existing text into the name

- **WHEN** a line stored before this change holds the description "Cloudflare
  Pro subscription"
- **THEN** after migration its `item_name` is "Cloudflare Pro subscription" and
  its `description` is null

#### Scenario: Migration carries a human's settled field with the value

- **WHEN** a line whose `verified_fields` contains `description` is migrated
- **THEN** its `verified_fields` contains `item_name` and no longer contains
  `description`, so a sync still cannot overwrite the value a human settled
