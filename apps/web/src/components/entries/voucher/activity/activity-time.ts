const dayFormatter = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' })
const timeFormatter = new Intl.DateTimeFormat('en-GB', { timeStyle: 'short' })
const fullFormatter = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

function parse(value: string): Date | null {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

/** A local-day key such as "2026-08-09", or "unknown" when unparseable. */
export function dayKey(value: string): string {
  const parsed = parse(value)
  if (!parsed) {
    return 'unknown'
  }
  const month = String(parsed.getMonth() + 1).padStart(2, '0')
  const day = String(parsed.getDate()).padStart(2, '0')
  return `${parsed.getFullYear()}-${month}-${day}`
}

/** "Today", "Yesterday" or a date such as "9 Aug 2026". */
export function dayLabel(value: string, now: Date = new Date()): string {
  const parsed = parse(value)
  if (!parsed) {
    return 'Unknown date'
  }
  const daysAgo = Math.round(
    (startOfDay(now) - startOfDay(parsed)) / 86_400_000,
  )
  if (daysAgo === 0) {
    return 'Today'
  }
  if (daysAgo === 1) {
    return 'Yesterday'
  }
  return dayFormatter.format(parsed)
}

/** The time of day, such as "14:05", or the raw value when unparseable. */
export function timeOfDay(value: string): string {
  const parsed = parse(value)
  return parsed ? timeFormatter.format(parsed) : value
}

/** The full date and time, such as "9 Aug 2026, 14:05". */
export function fullDateTime(value: string): string | undefined {
  const parsed = parse(value)
  return parsed ? fullFormatter.format(parsed) : undefined
}
