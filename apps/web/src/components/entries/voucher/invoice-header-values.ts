import { toNumber } from '#/lib/format/format'
import type { InvoiceDetailRead, InvoiceUpdate } from '#/lib/api/types'

export interface HeaderValues {
  /** The invoice number printed on the document. */
  document_invoice_number: string
  invoice_date: string
  currency: string
  /** The parsed amount, not the input text. */
  total: number | null
  tax: number | null
  vendor_id: string
  supplier_name: string
  supplier_country_code: string
  supplier_vat_number: string
}

export const TEXT_FIELDS = [
  'document_invoice_number',
  'invoice_date',
  'currency',
  'vendor_id',
  'supplier_name',
  'supplier_country_code',
  'supplier_vat_number',
] as const

export const NUMBER_FIELDS = ['total', 'tax'] as const

export function headerValuesFrom(invoice: InvoiceDetailRead): HeaderValues {
  const text = (value: string | null) => value ?? ''
  const money = (value: InvoiceDetailRead['total']) => {
    if (value === null || value === undefined) {
      return null
    }
    const parsed = toNumber(value)
    return Number.isNaN(parsed) ? null : parsed
  }
  return {
    document_invoice_number: text(invoice.document_invoice_number),
    invoice_date: text(invoice.invoice_date),
    currency: text(invoice.currency),
    total: money(invoice.total),
    tax: money(invoice.tax),
    vendor_id: text(invoice.vendor_id),
    supplier_name: text(invoice.supplier_name),
    supplier_country_code: text(invoice.supplier_country_code),
    supplier_vat_number: text(invoice.supplier_vat_number),
  }
}

/** The changed fields as an invoice update, with cleared fields as `null`. */
export function toInvoiceUpdate(
  current: HeaderValues,
  original: HeaderValues,
): InvoiceUpdate {
  const changes: InvoiceUpdate = {}
  for (const field of TEXT_FIELDS) {
    if (current[field] !== original[field]) {
      changes[field] = current[field] || null
    }
  }
  for (const field of NUMBER_FIELDS) {
    if (current[field] !== original[field]) {
      changes[field] = current[field]
    }
  }
  return changes
}

export function isDirty(
  current: HeaderValues,
  original: HeaderValues,
): boolean {
  return [...TEXT_FIELDS, ...NUMBER_FIELDS].some(
    (f) => current[f] !== original[f],
  )
}
