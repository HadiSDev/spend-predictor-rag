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
  /** The spend tree this company categorizes against; its name is resolved
   *  server-side so a picker can label it without a second request. */
  spend_tree_id: string | null
  spend_tree_name: string | null
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
  /** Omitted means the organization's copy of the default template, created on
   *  the spot if this is its first company. */
  spend_tree_id?: string | null
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

/** Body of `POST /erp-integrations/{id}/replace`. Moves the company to a
 *  different ERP: the old integration is soft-disconnected, not deleted. */
export interface ErpIntegrationReplace {
  erp_type: string
  label?: string | null
  credentials: Record<string, string>
  /** Acknowledges that the old ERP's rows stay and the new one will re-deliver
   *  overlapping periods, so those periods are counted twice. */
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
  /**
   * Changing this does not rewrite already-converted rows — they keep the
   * currency they were converted to until a recompute rewrites them.
   */
  base_currency?: string
  /**
   * Changing this re-points every line whose stored path exists in the new tree
   * and clears the rest, in the same transaction. Nothing is rewritten and no
   * verification is lost; the response reports how many lines were left needing
   * review.
   */
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

/** What `POST /companies/{id}/recompute-fx` reports back. Counts are rows. */
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

/**
 * What `POST /companies/{id}/recategorize` reports back.
 *
 * `queued` is lines *queued*, never lines categorized: the web API cannot
 * categorize anything, so the lines wait for the next sync run.
 */
export interface RecategorizeResult {
  company_id: string
  queued: number
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
  /**
   * The voucher's invoice lines — what the table lists when a group is
   * expanded. Empty for a voucher with no source invoice (a journal entry, a
   * transfer), which is ordinary rather than an error.
   *
   * Already ordered by the server, in the order the line's source stated it.
   * Do not re-sort by id: an invoice reads top to bottom.
   */
  lines: Array<InvoiceLineRead>
  /** The invoice's document-processing state, or null when the voucher has no
   *  source invoice. See `DocStatus`. */
  doc_status: DocStatus | null
  doc_error: string | null
  /** The invoice's number as the ERP posted it. Often a fallback identifier
   *  rather than the supplier's — Billy uses the bill id when the customer left
   *  the field blank. */
  invoice_number: string | null
  /** The number printed on the scan. Preferred for display; the two disagreeing
   *  is information, not noise to resolve silently. */
  document_invoice_number: string | null
}

/**
 * Whether an invoice's attached document has been turned into lines.
 *
 * Deliberately separate from the invoice's categorization status: one says
 * whether we have read the document, the other whether the resulting spend has
 * been categorized. `not_applicable` is the ordinary state for a voucher with
 * no scan — most of them — and is not a failure.
 */
export type DocStatus = 'not_applicable' | 'pending' | 'processing' | 'processed' | 'failed'

/**
 * Which source produced an invoice line.
 *
 * `entry_fallback` stands in for one expense posting because no document was
 * read. It is a real line in every respect — categorizable, verifiable — but
 * its description is the bookkeeper's memo, not what was bought, so the reader
 * is told. Stored on the line rather than inferred: a stand-in and an extracted
 * line can be identical in every other field.
 *
 * `human` is a line a reviewer wrote by hand, typically splitting a stand-in
 * into what was actually bought. It outranks every other origin, so no sync or
 * extraction displaces it.
 */
export type LineOrigin = 'erp' | 'document_ai' | 'entry_fallback' | 'human'

/** Which face of the voucher panel is showing. */
export type VoucherTab = 'details' | 'lines' | 'postings' | 'activity'

/** Filters accepted by both entry list endpoints. Unset keys are not sent. */
export interface EntryFilters {
  company_id?: string
  entry_type?: string
  status?: string
  vendor_id?: string
  /** Line provenance — finds the spend still standing on its postings. */
  origin?: LineOrigin
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

/** Fields `POST /invoice-lines/{id}/verify` accepts as corrections. Only the
 *  levels are editable here — everything else on the line is either evidence
 *  (amount, description) or derived server-side (account_code/name). */
/**
 * A correction to a line's category. In practice only `spend_category_id` is
 * ever sent: the server derives the levels from the chosen node's path, so a
 * correction always resolves to a real row. The level keys remain in the type
 * because the API still accepts them, not because the UI produces them.
 */
export type LineCorrections = Partial<
  Record<'level_1' | 'level_2' | 'level_3' | 'level_4' | 'spend_category_id', string>
>

/** One line of an invoice, holding its categorization result directly. */
export interface InvoiceLineRead {
  id: string
  invoice_id: string
  company_id: string
  /** What was bought, named. The line's primary label; `description` is prose
   *  the supplier printed alongside it, and is frequently null. Which to show
   *  is the client's call, so the server sends both rather than folding one
   *  into the other. */
  item_name: string | null
  description: string | null
  quantity: Money | null
  /** What `quantity` counts — `pcs`, `hours`. Null is the ordinary case: an ERP
   *  bill line states no unit, and none is ever substituted. */
  unit: string | null
  unit_price: Money | null
  amount: Money | null
  native_account_code: string | null
  /** Which source produced this line — decides whether its description can be
   *  trusted as what was bought. */
  origin: LineOrigin
  /** Position on the invoice, as its source stated it. The server already
   *  orders by this; carried so a client-side sort can restore it. */
  sequence: number
  /** The currency `amount` is in. A line has none of its own — this is its
   *  invoice's, resolved server-side. */
  currency: string | null
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
  /** Set only when the company's spend tree is four levels deep. */
  level_4: string | null
  account_code: string | null
  account_name: string | null
  confidence: Money | null
  rationale: string | null
  spend_category_id: string | null
  /**
   * The line carries a categorization that no longer resolves to a node — the
   * company's tree changed, or the node was deleted. Server-computed: a client
   * cannot know which tree a company is on without a second request, and a
   * stale category shown as a settled one is the failure the stored pointer
   * exists to prevent. Distinct from `ai_failed`: nothing failed, the taxonomy
   * moved.
   */
  category_stale: boolean
  /** Which of this line's fields a human has settled. A sync refreshes
   *  everything else from the ERP and leaves these alone. */
  verified_fields: Array<string>
}

/** An invoice header. */
export interface InvoiceRead {
  id: string
  company_id: string
  vendor_id: string | null
  invoice_number: string | null
  /** The number printed on the scan, beside the as-posted one rather than over
   *  it — extraction never rewrites the ERP's value. */
  document_invoice_number: string | null
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
  /** The supplier this invoice states: the human's override when one was made,
   *  otherwise the linked vendor's value. Resolved server-side — the fallback
   *  is a rule, and a rule reimplemented per client eventually differs. */
  supplier_name: string | null
  supplier_country_code: string | null
  supplier_vat_number: string | null
  /** Which of the three above are the human's rather than the catalog's, so a
   *  corrected supplier is distinguishable from a catalogued one. */
  supplier_overrides: Array<string>
  status: string
  /** `erp` | `pdf_extraction`. Provenance only: it says how much to trust a
   *  value, not whether the value may be corrected. */
  source: string
  /** Which fields a human has settled, and who settled them when. Per field,
   *  so a sync still refreshes everything nobody has spoken for. */
  verified_fields: Array<string>
  verified_at: string | null
  verified_by: string | null
  error_message: string | null
  file_id: string | null
  /** Resolved from the linked File so a client never needs a second lookup to
   *  decide whether to render a viewer. */
  file_name: string | null
  has_document: boolean
  /** Whether the attached document has been turned into lines. Separate from
   *  `status` above, which is the categorization rollup. */
  doc_status: DocStatus
  /** Why the last extraction failed, in words meant for the user — it is shown
   *  beside the retrigger action, not only logged. */
  doc_error: string | null
  doc_processed_at: string | null
}

/** `InvoiceRead` plus its lines — the shape a voucher's detail panel needs. */
export interface InvoiceDetailRead extends InvoiceRead {
  lines: Array<InvoiceLineRead>
  /** Do the lines add up to the header? Server-computed through the same rule
   *  that accepts or rejects an extraction, so the two can never disagree. */
  lines_reconciled: boolean
  /** Signed `sum(lines) − nearest accepted total`, so a reader can see which
   *  way it is out. Null when the lines reconcile or there is no total. */
  reconciliation_delta: Money | null
}

/**
 * `PATCH /invoices/{id}` — corrections to a parsed invoice header.
 *
 * Not gated on provenance: an ERP-posted header is as correctable as an
 * extracted one. The `supplier_*` fields are invoice-scoped overrides and never
 * write through to the global `Vendor` row; `vendor_id` is the other, different
 * correction — "this is the wrong supplier" rather than "this supplier's
 * details are wrong on this document".
 */
export interface InvoiceUpdate {
  /** The number printed on the scan — what a human reconciles against, and
   *  what a model may have misread. `invoice_number` beside it is the ERP's
   *  as-posted value, shown as evidence rather than offered for editing. */
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

/**
 * `POST /invoices/{id}/verify` — the same fields, plus the act of verifying.
 *
 * A separate call from the PATCH because "I looked, and it was right" is a
 * signal a correction cannot express, and it is the label the extractor needs.
 * An empty body is the whole point of it.
 */
export type InvoiceVerify = InvoiceUpdate

/**
 * `PATCH /invoice-lines/{id}` — what a line says was bought.
 *
 * Not the spend category: that goes through `verify`, which resolves it against
 * the company's tree. The server rejects a category sent here rather than
 * ignoring it, so the mistake is loud.
 */
export interface InvoiceLineUpdate {
  item_name?: string | null
  description?: string | null
  quantity?: number | null
  unit?: string | null
  unit_price?: number | null
  amount?: number | null
}

/** `POST /invoices/{id}/lines` — a line a reviewer adds by hand. `origin` is
 *  not a parameter: it is `human` by construction. */
export interface InvoiceLineCreate extends InvoiceLineUpdate {
  /** Omitted means "after the last line", which is what appending means. */
  sequence?: number
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
