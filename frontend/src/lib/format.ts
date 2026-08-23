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

/**
 * Words that are acronyms rather than ordinary words, so sentence-casing them
 * would produce "Ai categorized" or "Vat" — visibly wrong in a way a reader
 * blames on us, not on the ERP.
 */
const ACRONYMS: Record<string, string> = {
  ai: 'AI',
  erp: 'ERP',
  vat: 'VAT',
  fx: 'FX',
  gl: 'GL',
}

/**
 * A machine key rendered as something a person reads: `purchase_invoice` →
 * `Purchase invoice`, `ai_categorized` → `AI categorized`.
 *
 * Needed because these values are not a fixed vocabulary we could hand-label.
 * The entry types offered as filters come from the org's own data, and
 * connectors are free to emit their own — so a lookup table would silently fall
 * back to the raw key for anything it had not been told about, which is the
 * behaviour being fixed. This degrades to "readable" instead.
 */
export function humanizeKey(value: string): string {
  const words = value.trim().replace(/[_-]+/g, ' ').split(/\s+/).filter(Boolean)
  if (words.length === 0) return value
  return words
    .map((word, i) => {
      const acronym = ACRONYMS[word.toLowerCase()]
      if (acronym) return acronym
      // Only the first word is capitalized: this is a label, not a title, and
      // "Purchase Invoice" reads as a proper noun.
      return i === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word
    })
    .join(' ')
}


/**
 * A `Date` as the `YYYY-MM-DD` string the API takes — and that
 * `<input type=date>` uses.
 *
 * Built from the **local** date parts rather than `toISOString()`, which
 * converts to UTC first: a date picked as the 1st in Copenhagen is `…T00:00:00`
 * local, which is the previous day in UTC, so `toISOString().slice(0, 10)`
 * silently reports the 31st. An invoice date is a calendar date with no time
 * and no zone, and it must survive the round trip unchanged.
 */
export function toIsoDate(date: Date | undefined): string | undefined {
  if (!date) return undefined
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/**
 * The inverse: an ISO date string as a local `Date`, or `undefined` if it is
 * not one.
 *
 * The explicit `T00:00:00` is what keeps it local — `new Date('2026-08-20')`
 * is parsed as UTC midnight by specification, which lands on the 19th for any
 * viewer behind UTC.
 */
export function fromIsoDate(value: string | undefined | null): Date | undefined {
  if (!value) return undefined
  const parsed = new Date(`${value}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? undefined : parsed
}
