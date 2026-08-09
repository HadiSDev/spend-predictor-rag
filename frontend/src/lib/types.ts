/** Response types mirroring the web API's Pydantic schemas (`web_api/schemas.py`). */

/** Decimal fields arrive as strings (Pydantic JSON) or numbers; coerce on use. */
export type Money = string | number

/** `GET /users/me` — the current principal. */
export interface UserRead {
  id: string
  email: string
  name: string
  role: string
  is_system_admin: boolean
  organization_id: string
}

/** `GET /organization` — the caller's organization profile. */
export interface OrganizationRead {
  id: string
  name: string
  slug: string | null
  /** `active` | `suspended`. */
  status: string
  created_at: string
}

/** `PATCH /organization` — partial update of the organization profile. */
export interface OrganizationUpdate {
  name?: string
  slug?: string
}

/** A company (legal entity) under the organization. */
export interface CompanyRead {
  id: string
  name: string
  country_code: string | null
  vat_number: string | null
  /** ISO 4217 code every figure for this company is presented in. */
  base_currency: string
  is_active: boolean
  deactivated_at: string | null
}

/** One credential input an ERP connector declares. Describes the field, never a value. */
export interface CredentialFieldRead {
  name: string
  label: string
  required: boolean
  secret: boolean
  default: string | null
}

/** Row of `GET /erp-types` — a connector this deployment can connect to. */
export interface ErpTypeRead {
  erp_type: string
  label: string
  credential_fields: Array<CredentialFieldRead>
  /** Names vendored artwork in `src/assets/erp`. Absent when we have none. */
  brand_slug?: string | null
  /** One line about the ERP, for the picker card. */
  description?: string | null
  docs_url?: string | null
}

/** The ERP connection to provision alongside a company. */
export interface IntegrationSpec {
  erp_type: string
  label?: string | null
  credentials?: Record<string, string>
}

/**
 * `POST /companies` — `name` and `integration` are both required: a company
 * with no ERP connection syncs nothing, so the two are created together.
 */
export interface CompanyCreate {
  name: string
  /** Required: a company whose figures cannot be presented is not usable. */
  base_currency: string
  country_code?: string | null
  vat_number?: string | null
  integration: IntegrationSpec
}

/** What `POST /companies` returns: the company plus the integration it got. */
export interface CompanyCreateResult extends CompanyRead {
  integration: ErpIntegrationRead
}

/** Non-secret view of an integration; credentials are reported, never returned. */
export interface ErpIntegrationRead {
  id: string
  company_id: string
  erp_type: string
  label: string | null
  connected_at: string | null
  disconnected_at: string | null
  created_at: string
  has_credentials: boolean
}

/** `POST /erp-integrations` — connect an ERP to a company that already exists. */
export interface ErpIntegrationCreate extends IntegrationSpec {
  company_id: string
}

/**
 * `PATCH /erp-integrations/{id}` — partial update. Omitting `credentials`
 * leaves the stored secret alone; supplying it replaces the map in full, since
 * that is how the API stores it.
 */
export interface ErpIntegrationUpdate {
  label?: string | null
  credentials?: Record<string, string>
}

/** `PATCH /companies/{id}` — partial update; omitted fields are left alone. */
export interface CompanyUpdate {
  name?: string
  country_code?: string | null
  vat_number?: string | null
  /**
   * Changing this does not rewrite already-converted rows — they keep the
   * currency they were converted to until a recompute rewrites them.
   */
  base_currency?: string
}

/** What `POST /companies/{id}/recompute-fx` reports back. Counts are rows. */
export interface FxRecomputeResult {
  company_id: string
  base_currency: string
  converted: number
  unconverted: number
  unchanged: number
}

/**
 * The conversion carried on every money-bearing payload: the same figure in the
 * company's currency, and the rate that got it there. All null together when
 * the row could not be converted — never zero.
 */
export interface Converted {
  base_currency: string | null
  fx_rate: string | number | null
  /** The publication the rate came from — not always the transaction's date. */
  fx_rate_date: string | null
}

/** Sums as converted (`base`, the default) or exactly as posted (`original`). */
export type CurrencyMode = 'base' | 'original'

/** Envelope for small aggregate reports (`Report[T]`). */
export interface Report<T> {
  rows: Array<T>
}

/** Row of `GET /reports/entries-summary`. */
export interface EntrySummaryRow {
  entry_type: string
  currency: string | null
  debit_total: Money
  credit_total: Money
  net: Money
  count: number
  /**
   * How many rows in this group had no base amount, and were left out of the
   * totals. Non-zero only on a base-mode row whose `currency` is null: that row
   * *is* the unconverted bucket, reported rather than hidden.
   */
  unconverted_count: number
}

/** Row of `GET /reports/spend-by-category`. */
export interface CategorySpendRow {
  level_2: string | null
  level_3: string | null
  currency: string | null
  amount_total: Money
  count: number
  /**
   * How many rows in this group had no base amount, and were left out of the
   * totals. Non-zero only on a base-mode row whose `currency` is null: that row
   * *is* the unconverted bucket, reported rather than hidden.
   */
  unconverted_count: number
}

/** Row of `GET /reports/spend-by-vendor`. */
export interface VendorSpendRow {
  vendor_id: string
  vendor_name: string
  currency: string | null
  amount_total: Money
  count: number
  /**
   * How many rows in this group had no base amount, and were left out of the
   * totals. Non-zero only on a base-mode row whose `currency` is null: that row
   * *is* the unconverted bucket, reported rather than hidden.
   */
  unconverted_count: number
}

/** A paginated result envelope (`Page[T]`). */
export interface Page<T> {
  items: Array<T>
  page: number
  page_size: number
  total: number
}

/** A supplier from the global vendor catalog (`GET /vendors`). */
export interface VendorRead {
  id: string
  name: string
  country_code: string | null
  vat_number: string | null
  description: string | null
}

/**
 * One raw GL posting. The account and supplier are resolved server-side — an
 * entry carries only foreign keys, and the vendor is not even one of them.
 */
export interface ErpEntryRead {
  id: string
  company_id: string
  erp_account_id: string
  source_invoice_id: string | null
  voucher_id: string | null
  entry_type: string
  accounting_date: string | null
  description: string | null
  debit_amount: Money | null
  credit_amount: Money | null
  currency: string | null
  erp_entry_id: string | null
  /** The same posting in the company's currency; null when unconverted. */
  base_debit_amount: Money | null
  base_credit_amount: Money | null
  status: string
  error_message: string | null
  created_at: string
  erp_account_code: string
  erp_account_name: string
  /** `expense` | `asset` | `liability` | `income`. Only expense postings are
   *  spend, which is why a voucher's total is not the sum of its rows. */
  erp_account_type: string | null
  vendor_id: string | null
  vendor_name: string | null
  /** The invoice line this posting came from. One line has many entries, so
   *  several postings can share it; null for VAT, the payable, a journal entry. */
  source_invoice_line_id: string | null
  /** The line's spend category, resolved server-side through that link. An
   *  entry is never itself categorized. All null both when there is no line and
   *  when the line is not categorized yet. */
  spend_category_level_1: string | null
  spend_category_level_2: string | null
  spend_category_level_3: string | null
}
export interface ErpEntryRead extends Converted {}

/**
 * The postings that make up one spend event (`GET /erp-entries/vouchers`).
 *
 * `currency`, `vendor_id`, and `vendor_name` are null when the group's entries
 * disagree. A null `currency` means the totals span currencies and must not be
 * rendered as one amount.
 */
export interface VoucherGroupRead {
  voucher_id: string | null
  company_id: string
  accounting_date: string | null
  entry_types: Array<string>
  entry_count: number
  /**
   * Signed net spend: debit − credit over the group's *expense* postings only.
   * Negative for a refund. Null when the voucher moved money without spending
   * any — a payment. Not `debit_total − credit_total`, which is zero for any
   * balanced voucher.
   */
  amount: Money | null
  /** Null only when every posting in the group is unconverted. */
  debit_total: Money | null
  credit_total: Money | null
  currency: string | null
  vendor_id: string | null
  vendor_name: string | null
  /**
   * How many postings have no base amount and are therefore *excluded* from the
   * totals above. Non-zero means the figure shown is incomplete.
   */
  unconverted_count: number
  entries: Array<ErpEntryRead>
}

/** Which face of the voucher panel is showing. */
export type VoucherTab = 'details' | 'postings' | 'activity'

/** Filters accepted by both entry list endpoints. Unset keys are not sent. */
export interface EntryFilters {
  company_id?: string
  entry_type?: string
  status?: string
  vendor_id?: string
  from?: string
  to?: string
  page?: number
  currency_mode?: CurrencyMode
  /** The open voucher, or the lone posting when it has no voucher id. */
  voucher?: string
  entry?: string
  tab?: VoucherTab
}

/**
 * One account from the ERP's chart. `is_active` mirrors the ERP; `sync_enabled`
 * and `with_vat` are ours — seeded from the ERP but never reset by it.
 */
export interface ErpAccountRead {
  id: string
  erp_integration_id: string
  erp_account_code: string
  erp_account_name: string
  erp_account_type: string | null
  parent_code: string | null
  is_active: boolean
  /** Whether the sync pulls this account's entries. Future ingestion only. */
  sync_enabled: boolean
  /** Whether this account is assumed VAT-inclusive when reconciling. */
  with_vat: boolean
}

/** `PATCH /erp-accounts/{id}` — only the two settings we own are writable. */
export interface ErpAccountUpdate {
  sync_enabled?: boolean
  with_vat?: boolean
}

/** `POST /erp-integrations/{id}/refresh-accounts`. */
export interface RefreshAccountsResult {
  seen: number
  added: number
}

/** One line of an invoice, holding its categorization result directly. */
export interface InvoiceLineRead {
  id: string
  invoice_id: string
  company_id: string
  description: string | null
  quantity: Money | null
  unit_price: Money | null
  amount: Money | null
  native_account_code: string | null
  /** The line in the company's base currency, at its invoice's rate. Null when
   *  unconverted. */
  base_currency: string | null
  base_amount: Money | null
  fx_rate: Money | null
  fx_rate_date: string | null
  /** `uncategorized` | `ai_failed` | `ai_categorized` | `verified`. */
  status: string
  level_1: string | null
  level_2: string | null
  level_3: string | null
  account_code: string | null
  account_name: string | null
  confidence: Money | null
  rationale: string | null
  spend_category_id: string | null
}

/** An invoice header. */
export interface InvoiceRead {
  id: string
  company_id: string
  vendor_id: string | null
  invoice_number: string | null
  invoice_date: string | null
  currency: string | null
  total: Money | null
  tax: Money | null
  /** The invoice in the company's base currency, at the rate in force on
   *  `invoice_date`. Null when unconverted. */
  base_currency: string | null
  base_total: Money | null
  base_tax: Money | null
  fx_rate: Money | null
  fx_rate_date: string | null
  status: string
  /** `erp` | `pdf_extraction`. */
  source: string
  error_message: string | null
  file_id: string | null
  /** Resolved from the linked File so a client never needs a second lookup to
   *  decide whether to render a viewer. */
  file_name: string | null
  has_document: boolean
}

/** `InvoiceRead` plus its lines — the shape a voucher's detail panel needs. */
export interface InvoiceDetailRead extends InvoiceRead {
  lines: Array<InvoiceLineRead>
}

/** The document attached to a voucher's invoice. Derived from
 *  `Invoice.file_id`/`File.filename` — never an independent source of truth. */
export interface DocumentRead {
  file_id: string
  filename: string
}

/**
 * Everything one voucher's detail panel needs, in one request.
 *
 * `amount`/`currency` follow the same `currency_mode=base|original` split as
 * `VoucherGroupRead` (base by default — see `voucherDetailQueryOptions`) and
 * are computed server-side by the very same rule the groups endpoint uses, so
 * a table row's total and the panel opened from it can never disagree. Do not
 * recompute either client-side.
 */
export interface VoucherDetailRead {
  voucher_id: string | null
  company_id: string
  accounting_date: string | null
  /** Claimed only when every summed posting agrees; null otherwise. */
  currency: string | null
  /** Signed net spend: debit - credit over the voucher's *expense* postings
   *  only. Null when the voucher moved money without spending any (a
   *  payment), or when nothing was summable at all. */
  amount: Money | null
  entry_count: number
  entries: Array<ErpEntryRead>
  invoice: InvoiceDetailRead | null
  document: DocumentRead | null
}

/** One audit-log row (`web_api/schemas.py::AuditLogRead`). */
export interface AuditLogRead {
  id: string
  entity_type: string
  entity_id: string
  action: string
  actor: string
  /** `diff_changes` in `web_api/audit.py` emits `{field, old, new}`. */
  changes: Array<{ field: string; old: unknown; new: unknown }> | null
  created_at: string
}

/** An audit row with the thing it happened to already named. */
export interface VoucherAuditRead extends AuditLogRead {
  entity_label: string
}
