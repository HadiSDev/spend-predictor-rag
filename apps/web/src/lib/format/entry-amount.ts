import { toNumber } from './format'
import type { ErpEntryRead } from '#/lib/api/types'

/** Signed spend for one posting: a credit on an expense account is a refund. */
export function postingAmount(entry: ErpEntryRead): number {
  return toNumber(entry.debit_amount ?? 0) - toNumber(entry.credit_amount ?? 0)
}

/** The same figure in the company's currency, or null when it was not converted. */
export function basePostingAmount(entry: ErpEntryRead): number | null {
  if (entry.base_currency === null) {
    return null
  }
  return (
    toNumber(entry.base_debit_amount ?? 0) -
    toNumber(entry.base_credit_amount ?? 0)
  )
}
