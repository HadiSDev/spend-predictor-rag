import type {
  CompanyDeleteBlocked,
  CompanyRead,
  ErpIntegrationRead,
  ErpTypeRead,
  ReplaceBlocked,
} from '#/lib/api/types'
import { findCountry } from '#/lib/format/countries'

export interface CompanyValues {
  name: string
  country_code: string
  vat_number: string
  /** ISO 4217 reporting currency. */
  base_currency: string
  /** The spend tree to categorize against; empty means the organization's default. */
  spend_tree_id: string
}

/** Company fields plus the ERP connection created alongside it. */
export interface CompanyCreateValues extends CompanyValues {
  erp_type: string
  credentials: Record<string, string>
}

/** Every field the company dialogs bind to. */
export interface CompanyFormValues extends CompanyCreateValues {
  label: string
  replaceCredentials: boolean
}

/** What `PATCH /erp-integrations/{id}` is asked to change. */
export interface IntegrationChanges {
  label?: string | null
  /** Replaces the whole stored credential map. */
  credentials?: Record<string, string>
}

/** A company's integrations, connected ones first. */
export function integrationsFor(
  integrations: Array<ErpIntegrationRead>,
  companyId: string,
): Array<ErpIntegrationRead> {
  const own = integrations.filter((row) => row.company_id === companyId)
  return [
    ...own.filter((row) => row.disconnected_at === null),
    ...own.filter((row) => row.disconnected_at !== null),
  ]
}

export function toValues(company: CompanyRead): CompanyValues {
  return {
    name: company.name,
    country_code:
      findCountry(company.country_code)?.code ?? company.country_code ?? '',
    vat_number: company.vat_number ?? '',
    base_currency: company.base_currency,
    spend_tree_id: company.spend_tree_id ?? '',
  }
}

/** The credential inputs start from whatever defaults the connector declares. */
export function defaultCredentials(
  erpType: ErpTypeRead | undefined,
): Record<string, string> {
  if (!erpType) {
    return {}
  }
  return Object.fromEntries(
    erpType.credential_fields.map((field) => [field.name, field.default ?? '']),
  )
}

/** The company fields, without the ERP connection. */
function companyFields(values: CompanyValues): CompanyValues {
  return {
    name: values.name,
    country_code: values.country_code,
    vat_number: values.vat_number,
    base_currency: values.base_currency,
    spend_tree_id: values.spend_tree_id,
  }
}

/** The fields that actually changed, so a PATCH stays a partial update. */
export function changedFields(
  before: CompanyValues,
  after: CompanyValues,
): Partial<CompanyValues> {
  const changes: Partial<CompanyValues> = {}
  for (const key of Object.keys(companyFields(after)) as Array<
    keyof CompanyValues
  >) {
    if (after[key] !== before[key]) {
      changes[key] = after[key]
    }
  }
  return changes
}

/** The 409 body of a blocked replacement, or null for any other failure. */
export function replaceBlockedFrom(err: unknown): ReplaceBlocked | null {
  const body = (err as { body?: { detail?: unknown } } | null)?.body?.detail
  if (!body || typeof body !== 'object') {
    return null
  }
  const detail = body as Partial<ReplaceBlocked>
  return typeof detail.entries === 'number' &&
    typeof detail.invoices === 'number'
    ? (detail as ReplaceBlocked)
    : null
}

/** The 409 body of a blocked deletion, or null for any other failure. */
export function deleteBlockedFrom(err: unknown): CompanyDeleteBlocked | null {
  const body = (err as { body?: { detail?: unknown } } | null)?.body?.detail
  if (!body || typeof body !== 'object') {
    return null
  }
  const detail = body as Partial<CompanyDeleteBlocked>
  return typeof detail.invoices === 'number' &&
    typeof detail.entries === 'number'
    ? (detail as CompanyDeleteBlocked)
    : null
}
