import type { Money } from '#/lib/api/types'

/** Coerce a Decimal-as-string|number money value to a number. */
export function toNumber(value: Money): number {
  return typeof value === 'number' ? value : Number(value)
}

/** Format an amount for display. */
export function formatMoney(value: Money, currency: string | null): string {
  const amount = toNumber(value)
  if (currency) {
    try {
      return new Intl.NumberFormat('en-GB', {
        style: 'currency',
        currency,
        maximumFractionDigits: 2,
      }).format(amount)
    } catch {}
    return `${new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 }).format(amount)} ${currency}`
  }
  return new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 }).format(
    amount,
  )
}

/** Compact integer formatting for counts. */
export function formatCount(value: number): string {
  return new Intl.NumberFormat('en-GB').format(value)
}

/** Words kept upper-case when humanizing a key. */
const ACRONYMS: Record<string, string> = {
  ai: 'AI',
  erp: 'ERP',
  vat: 'VAT',
  fx: 'FX',
  gl: 'GL',
}

/** A machine key rendered as human-readable text. */
export function humanizeKey(value: string): string {
  const words = value.trim().replace(/[_-]+/g, ' ').split(/\s+/).filter(Boolean)
  if (words.length === 0) {
    return value
  }
  return words
    .map((word, i) => {
      const acronym = ACRONYMS[word.toLowerCase()]
      if (acronym) {
        return acronym
      }
      return i === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word
    })
    .join(' ')
}

/** A `Date` as a `YYYY-MM-DD` string. */
export function toIsoDate(date: Date | undefined): string | undefined {
  if (!date) {
    return undefined
  }
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/** An ISO date string as a local `Date`, or `undefined` if it is not one. */
export function fromIsoDate(
  value: string | undefined | null,
): Date | undefined {
  if (!value) {
    return undefined
  }
  const parsed = new Date(`${value}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? undefined : parsed
}
