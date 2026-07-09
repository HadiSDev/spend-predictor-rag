import type { Money } from './types'

/** Coerce a Decimal-as-string|number money value to a number. */
export function toNumber(value: Money): number {
  return typeof value === 'number' ? value : Number(value)
}

/**
 * Format an amount for display. When a currency is known, use the currency
 * style; otherwise fall back to a plain grouped number. Amounts are never
 * combined across currencies by callers — the API groups by currency.
 */
export function formatMoney(value: Money, currency: string | null): string {
  const amount = toNumber(value)
  if (currency) {
    try {
      return new Intl.NumberFormat('en-GB', {
        style: 'currency',
        currency,
        maximumFractionDigits: 2,
      }).format(amount)
    } catch {
      // Unknown/invalid currency code → fall through to number + code.
    }
    return `${new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 }).format(amount)} ${currency}`
  }
  return new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 }).format(amount)
}

/** Compact integer formatting for counts. */
export function formatCount(value: number): string {
  return new Intl.NumberFormat('en-GB').format(value)
}
