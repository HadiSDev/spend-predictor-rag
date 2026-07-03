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

The categorizer maps ErpEntry records to the spend tree by looking at their ERP account, description, and associated invoice context.

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
| level1 | text | "Direct" | "Indirect", nullable until categorized |
| level2 | text | From spend tree, nullable until categorized |
| level3 | text | Nullable |
| account_code | text | Chosen spend tree leaf code, nullable until categorized |
| account_name | text | Chosen spend tree leaf name, nullable |
| confidence | numeric(4,3) | Nullable until categorized |
| rationale | text | Nullable |
| gt_level1 | text | Ground truth (synthetic only) |
| gt_level2 | text | Ground truth (synthetic only) |
| gt_level3 | text | Ground truth (synthetic only) |
| gt_account_code | text | Ground truth (synthetic only) |
| raw_json | jsonb | Original ERP entry data |
| created_at | timestamptz | |

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

### Requirement: Spend-tree nodes are modeled as SpendCategory

The company spend-tree node SHALL be the `SpendCategory` entity, stored in the `spend_categories` table, replacing the former `Account`/`accounts` naming which collided with the ERP's native `ErpAccount`.

- A `SpendCategory` SHALL belong to a Company (`company_id` FK → companies).
- The Company relationship SHALL be exposed as `Company.spend_categories`.
- `account_code`, `account_name`, and `description` SHALL remain on the node as
  the leaf identity and embedding text used for retrieval and categorization.

#### Scenario: Spend categories are scoped to a company

- **WHEN** a company's spend tree is loaded
- **THEN** each node is a `SpendCategory` row with that `company_id`, reachable via
  `Company.spend_categories`

### Requirement: SpendCategory stores four labelled levels including Direct/Indirect

`SpendCategory` SHALL store an explicit level path `level_1`, `level_2`, `level_3`, `level_4`, where `level_1` holds the Direct/Indirect classification that was previously inferred and never persisted.

- `level_1` SHALL hold the Direct/Indirect value and SHALL be stored on the node
  (nullable when not yet classified). This supersedes the prior rule that L1 is
  never stored.
- `level_2` SHALL be required (the top category).
- `level_3` and `level_4` SHALL be optional (subcategory and deepest tier).
- The former `level2` and `level3` fields SHALL be migrated to `level_2` and
  `level_3` respectively.

#### Scenario: Direct/Indirect is stored on the node

- **WHEN** a spend category is classified as Direct or Indirect
- **THEN** its `level_1` field holds that value

#### Scenario: Optional deeper levels

- **WHEN** a company's tree uses only two labelled tiers
- **THEN** the node has `level_2` set and `level_3` / `level_4` null, and remains
  valid

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

#### Scenario: Disabled account is excluded from entry ingestion

- **WHEN** an `ErpAccount` has `sync_enabled = false`
- **THEN** the sync does not fetch or persist any `ErpEntry` for that account

#### Scenario: Selection survives a re-sync

- **WHEN** an account is toggled `sync_enabled = false` and the ERP accounts are
  fetched again on the next sync
- **THEN** the account's `sync_enabled` stays `false` while its name/type/VAT
  metadata are refreshed

### Requirement: ErpAccount records whether it is with or without VAT

`ErpAccount` SHALL carry a `with_vat` boolean, read from the ERP account, recording whether the account is configured with VAT or without VAT.

- `with_vat` SHALL be populated from the ERP account data during account sync.
- `with_vat` is metadata only in this change: no amount is recomputed from it. It
  exists so later categorization can decide whether to sum invoice lines including
  or excluding VAT when reconciling predicted totals against posted entries.

#### Scenario: VAT flag is stored from the ERP account

- **WHEN** the ERP reports an account as with-VAT
- **THEN** the persisted `ErpAccount` has `with_vat = true`

#### Scenario: Without-VAT account is stored as such

- **WHEN** the ERP reports an account as without-VAT
- **THEN** the persisted `ErpAccount` has `with_vat = false`

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

