/** Response types mirroring the web API's Pydantic schemas (`web_api/schemas.py`). */

/** A decimal field, as a string or a number. */
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
  /** The spend tree this company categorizes against. */
  spend_tree_id: string | null
  spend_tree_name: string | null
}

/** One credential input an ERP connector declares. */
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
  /** Names vendored artwork in `src/assets/erp`. */
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

/** `POST /companies` — a company together with its ERP integration. */
export interface CompanyCreate {
  name: string
  base_currency: string
  country_code?: string | null
  vat_number?: string | null
  integration: IntegrationSpec
  /** Omitted means the organization's copy of the default template. */
  spend_tree_id?: string | null
}

/** What `POST /companies` returns: the company plus the integration it got. */
export interface CompanyCreateResult extends CompanyRead {
  integration: ErpIntegrationRead
}

/** Non-secret view of an integration. */
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

/** `PATCH /erp-integrations/{id}` — partial update. */
export interface ErpIntegrationUpdate {
  label?: string | null
  credentials?: Record<string, string>
}

/** Body of `POST /erp-integrations/{id}/replace`. */
export interface ErpIntegrationReplace {
  erp_type: string
  label?: string | null
  credentials: Record<string, string>
  /** Acknowledges that overlapping periods will be counted twice. */
  confirm?: boolean
}

/** The 409 body when a replacement would double already-posted spend. */
export interface ReplaceBlocked {
  detail: string
  invoices: number
  entries: number
  earliest: string | null
  latest: string | null
}

/** `PATCH /companies/{id}` — partial update; omitted fields are left alone. */
export interface CompanyUpdate {
  name?: string
  country_code?: string | null
  vat_number?: string | null
  base_currency?: string
  spend_tree_id?: string | null
}

/** What `PATCH /companies/{id}` returns: the company plus what the change cost. */
export interface CompanyUpdateResult extends CompanyRead {
  /** Lines left carrying a category that no longer resolves. */
  stale_lines: number
}

/** One node of a spend tree. Carries both its parentage and its full path. */
export interface SpendCategoryRead {
  id: string
  spend_tree_id: string
  parent_id: string | null
  depth: number
  name: string
  code: string | null
  sort_order: number
  description: string | null
  level_1: string | null
  level_2: string | null
  level_3: string | null
  level_4: string | null
}

/** A spend tree in the list view. */
export interface SpendTreeRead {
  id: string
  name: string
  /** 3 or 4. The default-template copy is fixed at 3. */
  max_depth: number
  /** `default_template` — the organization's own copy — or `custom`. */
  source: 'default_template' | 'custom'
  template_version: string | null
  archived_at: string | null
  created_at: string
  node_count: number
  company_ids: Array<string>
  company_names: Array<string>
}

/** `GET /spend-trees/{id}` — one tree with every node, ordered shallowest first. */
export interface SpendTreeDetailRead extends SpendTreeRead {
  nodes: Array<SpendCategoryRead>
}

/** `POST /spend-trees` — empty, or cloned from `source_tree_id`. */
export interface SpendTreeCreate {
  name: string
  max_depth?: number
  source_tree_id?: string | null
}

export interface SpendTreeUpdate {
  name?: string
  max_depth?: number
}

export interface SpendCategoryCreate {
  name: string
  parent_id?: string | null
  code?: string | null
  description?: string | null
  sort_order?: number
}

export interface SpendCategoryUpdate {
  name?: string
  parent_id?: string | null
  code?: string | null
  description?: string | null
  sort_order?: number
}

/** One rejected import row, addressed by its line number in the uploaded file. */
export interface SpendTreeImportError {
  line: number
  message: string
}

export interface SpendTreeImportResult {
  created: number
  updated: number
  removed: number
  stale_lines: number
}

/** Deleting a node reports what it cost, in lines that now need review. */
export interface SpendTreeDeleteResult {
  stale_lines: number
}

/** What a company holds, or held — the figures a deletion is judged by. */
export interface CompanyRecordCounts {
  invoices: number
  lines: number
  entries: number
  integrations: number
  earliest: string | null
  latest: string | null
}

/** The `409` body when a deletion needs confirming: what it *would* destroy. */
export interface CompanyDeleteBlocked extends CompanyRecordCounts {
  detail: string
}

/** What a completed deletion destroyed. */
export interface CompanyDeleteResult extends CompanyRecordCounts {
  id: string
  name: string
}

export interface FxRecomputeResult {
  company_id: string
  base_currency: string
  converted: number
  unconverted: number
  unchanged: number
}

/** What `POST /companies/{id}/recategorize` reports back. */
export interface RecategorizeResult {
  company_id: string
  queued: number
}

/** The conversion carried on every money-bearing payload. */
export interface Converted {
  base_currency: string | null
  fx_rate: string | number | null
  /** The publication date the rate came from. */
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
  /** Rows left out of the totals for lacking a base amount. */
  unconverted_count: number
}

/** Row of `GET /reports/spend-by-category`. */
export interface CategorySpendRow {
  level_2: string | null
  level_3: string | null
  currency: string | null
  amount_total: Money
  count: number
  /** Rows left out of the totals for lacking a base amount. */
  unconverted_count: number
}

/** Row of `GET /reports/spend-by-vendor`. */
export interface VendorSpendRow {
  vendor_id: string
  vendor_name: string
  currency: string | null
  amount_total: Money
  count: number
  /** Rows left out of the totals for lacking a base amount. */
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

/** One raw GL posting. */
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
  /** `expense` | `asset` | `liability` | `income`. */
  erp_account_type: string | null
  vendor_id: string | null
  vendor_name: string | null
  /** The invoice line this posting came from. */
  source_invoice_line_id: string | null
  /** The line's spend category, resolved server-side through that link. */
  spend_category_level_1: string | null
  spend_category_level_2: string | null
  spend_category_level_3: string | null
}
export interface ErpEntryRead extends Converted {}

/** The postings that make up one spend event (`GET /erp-entries/vouchers`). */
export interface VoucherGroupRead {
  voucher_id: string | null
  company_id: string
  accounting_date: string | null
  entry_types: Array<string>
  entry_count: number
  /** Signed net spend over the group's expense postings. */
  amount: Money | null
  /** Null only when every posting in the group is unconverted. */
  debit_total: Money | null
  credit_total: Money | null
  currency: string | null
  vendor_id: string | null
  vendor_name: string | null
  /** Postings left out of the totals for lacking a base amount. */
  unconverted_count: number
  entries: Array<ErpEntryRead>
  /** The voucher's invoice lines. */
  lines: Array<InvoiceLineRead>
  /** The invoice's document-processing state, if any. */
  doc_status: DocStatus | null
  doc_error: string | null
  /** The invoice's number as the ERP posted it. */
  invoice_number: string | null
  /** The number printed on the scan. */
  document_invoice_number: string | null
}

/** Whether an invoice's attached document has been turned into lines. */
export type DocStatus =
  'not_applicable' | 'pending' | 'processing' | 'processed' | 'failed'

/** Which source produced an invoice line. */
export type LineOrigin = 'erp' | 'document_ai' | 'entry_fallback' | 'human'

/** Which face of the voucher panel is showing. */
export type VoucherTab = 'details' | 'lines' | 'postings' | 'activity'

/** Filters accepted by both entry list endpoints. Unset keys are not sent. */
export interface EntryFilters {
  company_id?: string
  entry_type?: string
  status?: string
  vendor_id?: string
  /** Line provenance. */
  origin?: LineOrigin
  /** Only vouchers with a low-confidence AI line. */
  needs_review?: boolean
  from?: string
  to?: string
  page?: number
  currency_mode?: CurrencyMode
  /** The open voucher, or the lone posting when it has no voucher id. */
  voucher?: string
  entry?: string
  tab?: VoucherTab
}

/** One account from the ERP's chart. */
export interface ErpAccountRead {
  id: string
  erp_integration_id: string
  erp_account_code: string
  erp_account_name: string
  erp_account_type: string | null
  parent_code: string | null
  is_active: boolean
  /** Whether the sync pulls this account's entries. */
  sync_enabled: boolean
  /** Whether this account is assumed VAT-inclusive when reconciling. */
  with_vat: boolean
}

/** `PATCH /erp-accounts/{id}` — the writable account settings. */
export interface ErpAccountUpdate {
  sync_enabled?: boolean
  with_vat?: boolean
}

/** `POST /erp-integrations/{id}/refresh-accounts`. */
export interface RefreshAccountsResult {
  seen: number
  added: number
}

/** A correction to a line's category. */
export type LineCorrections = Partial<
  Record<
    'level_1' | 'level_2' | 'level_3' | 'level_4' | 'spend_category_id',
    string
  >
>

/** One line of an invoice, holding its categorization result directly. */
export interface InvoiceLineRead {
  id: string
  invoice_id: string
  company_id: string
  /** What was bought, named. */
  item_name: string | null
  description: string | null
  quantity: Money | null
  /** What `quantity` counts — `pcs`, `hours`. */
  unit: string | null
  unit_price: Money | null
  amount: Money | null
  native_account_code: string | null
  /** Which source produced this line. */
  origin: LineOrigin
  /** Position on the invoice, as its source stated it. */
  sequence: number
  /** The currency `amount` is in. */
  currency: string | null
  /** The line in the company's base currency, at its invoice's rate. */
  base_currency: string | null
  base_amount: Money | null
  fx_rate: Money | null
  fx_rate_date: string | null
  /** `uncategorized` | `ai_failed` | `ai_categorized` | `verified`. */
  status: string
  level_1: string | null
  level_2: string | null
  level_3: string | null
  /** Set only when the company's spend tree is four levels deep. */
  level_4: string | null
  account_code: string | null
  account_name: string | null
  confidence: Money | null
  rationale: string | null
  spend_category_id: string | null
  /** The line's categorization no longer resolves to a node. */
  category_stale: boolean
  /** The AI categorized this line with low confidence. */
  needs_review: boolean
  /** Which of this line's fields a human has settled. */
  verified_fields: Array<string>
}

/** An invoice header. */
export interface InvoiceRead {
  id: string
  company_id: string
  vendor_id: string | null
  invoice_number: string | null
  /** The number printed on the scan. */
  document_invoice_number: string | null
  invoice_date: string | null
  currency: string | null
  total: Money | null
  tax: Money | null
  /** The invoice in the company's base currency. */
  base_currency: string | null
  base_total: Money | null
  base_tax: Money | null
  fx_rate: Money | null
  fx_rate_date: string | null
  /** The supplier this invoice states. */
  supplier_name: string | null
  supplier_country_code: string | null
  supplier_vat_number: string | null
  /** Which supplier fields a human overrode. */
  supplier_overrides: Array<string>
  status: string
  /** `erp` | `pdf_extraction`. */
  source: string
  /** Which fields a human has settled, and who settled them when. */
  verified_fields: Array<string>
  verified_at: string | null
  verified_by: string | null
  error_message: string | null
  file_id: string | null
  file_name: string | null
  has_document: boolean
  /** Whether the attached document has been turned into lines. */
  doc_status: DocStatus
  /** Why the last extraction failed, in user-facing words. */
  doc_error: string | null
  doc_processed_at: string | null
  /** What the document stated about its own arithmetic. */
  document_total: Money | null
  document_tax: Money | null
  /** Do the two describe the same invoice? */
  totals_agree: boolean | null
}

/** `InvoiceRead` plus its lines — the shape a voucher's detail panel needs. */
export interface InvoiceDetailRead extends InvoiceRead {
  lines: Array<InvoiceLineRead>
  /** Do the lines add up to the header? */
  lines_reconciled: boolean
  /** Signed `sum(lines) − nearest accepted total`. */
  reconciliation_delta: Money | null
}

/** `PATCH /invoices/{id}` — corrections to a parsed invoice header. */
export interface InvoiceUpdate {
  /** The number printed on the scan. */
  document_invoice_number?: string | null
  invoice_number?: string | null
  invoice_date?: string | null
  currency?: string | null
  total?: number | null
  tax?: number | null
  vendor_id?: string | null
  supplier_name?: string | null
  supplier_country_code?: string | null
  supplier_vat_number?: string | null
}

/** `POST /invoices/{id}/verify` — the same fields, plus the act of verifying. */
export type InvoiceVerify = InvoiceUpdate

/** `PATCH /invoice-lines/{id}` — what a line says was bought. */
export interface InvoiceLineUpdate {
  item_name?: string | null
  description?: string | null
  quantity?: number | null
  unit?: string | null
  unit_price?: number | null
  amount?: number | null
}

/** `POST /invoices/{id}/lines` — a line a reviewer adds by hand. */
export interface InvoiceLineCreate extends InvoiceLineUpdate {
  /** Omitted means after the last line. */
  sequence?: number
}

/** The document attached to a voucher's invoice. */
export interface DocumentRead {
  file_id: string
  filename: string
}

/** Everything one voucher's detail panel needs, in one request. */
export interface VoucherDetailRead {
  voucher_id: string | null
  company_id: string
  accounting_date: string | null
  /** Claimed only when every summed posting agrees; null otherwise. */
  currency: string | null
  /** Signed net spend over the voucher's expense postings. */
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
  changes: Array<{ field: string; old: unknown; new: unknown }> | null
  created_at: string
}

/** An audit row with the thing it happened to already named. */
export interface VoucherAuditRead extends AuditLogRead {
  entity_label: string
  /** The user's name when a person made the change; null for the system. */
  actor_name?: string | null
}

/** One line that argued for a suggestion. */
export interface SuggestionEvidenceRead {
  id: string
  item_name: string | null
  description: string | null
  amount: Money | null
  currency: string | null
  vendor_name: string | null
  invoice_id: string | null
  /** Where the categorizer put the line. */
  level_1: string | null
  level_2: string | null
  level_3: string | null
  confidence: Money | null
}

/** A category the tree is missing, with where it would go and why. */
export interface SpendCategorySuggestionRead {
  id: string
  spend_tree_id: string
  company_id: string | null
  parent_id: string | null
  parent_path: string | null
  name: string
  description: string | null
  rationale: string | null
  /** `pending` | `accepted` | `dismissed`. */
  state: string
  created_category_id: string | null
  /** False once the parent it named has been deleted. */
  acceptable: boolean
  evidence: Array<SuggestionEvidenceRead>
  evidence_count: number
  created_at: string | null
}

export interface SuggestionResolveResult {
  id: string
  state: string
  created_category_id: string | null
}
