import { toNumber } from './format'
import type { ErpEntryRead } from './types'

/**
 * Signed spend for one posting: a credit on an expense account is a refund.
 *
 * The `?? 0` is load-bearing. Connectors send `0.00` rather than null on the
 * side a posting does not use, so subtracting is what collapses two columns
 * into one signed figure without printing a zero for the unused side.
 */
export function postingAmount(entry: ErpEntryRead): number {
  return toNumber(entry.debit_amount ?? 0) - toNumber(entry.credit_amount ?? 0)
}

/** The same figure in the company's currency, or null when it was not converted. */
export function basePostingAmount(entry: ErpEntryRead): number | null {
  if (entry.base_currency === null) return null
  return toNumber(entry.base_debit_amount ?? 0) - toNumber(entry.base_credit_amount ?? 0)
}
