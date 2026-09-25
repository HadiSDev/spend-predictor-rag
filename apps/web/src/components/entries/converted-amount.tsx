import { Tooltip, TooltipContent, TooltipTrigger, cn } from '#/components/ui'
import { formatMoney, toNumber } from '#/lib/format/format'
import type { Converted, Money } from '#/lib/api/types'

const rateDateFormatter = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium',
})

function formatRateDate(value: string | null): string {
  if (!value) {
    return 'an unknown date'
  }
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? value
    : rateDateFormatter.format(parsed)
}

/** Whether the row was converted at a rate other than 1. */
export function wasConverted(row: Converted): boolean {
  return (
    row.base_currency !== null &&
    row.fx_rate !== null &&
    toNumber(row.fx_rate) !== 1
  )
}

/** The posted amount, rate and rate date behind a converted figure. */
export function conversionSummary(
  row: Converted,
  posted: Money | null,
  postedCurrency: string | null,
): string {
  const original = formatMoney(posted ?? 0, postedCurrency)
  const rate =
    row.fx_rate === null
      ? '?'
      : toNumber(row.fx_rate).toLocaleString('en-GB', {
          maximumFractionDigits: 6,
        })
  return `${original} at ${rate} ${row.base_currency}/${postedCurrency}, rate of ${formatRateDate(row.fx_rate_date)}`
}

export interface ConvertedAmountProps {
  row: Converted
  /** The figure in the base currency; null when not converted. */
  base: Money | null
  /** The figure as the ERP posted it. */
  posted: Money | null
  postedCurrency: string | null
  className?: string
  /** Tint negative figures. */
  signed?: boolean
}

/** A monetary figure in the base currency with its conversion on hover or focus. */
export function ConvertedAmount({
  row,
  base,
  posted,
  postedCurrency,
  className,
  signed = false,
}: ConvertedAmountProps) {
  const tint = signed && base !== null && toNumber(base) < 0
  const hasNoAmount = base === null && posted === null

  if (hasNoAmount) {
    return <span className={cn('text-muted-foreground', className)}>—</span>
  }

  if (row.base_currency === null) {
    const shown = formatMoney(posted ?? 0, postedCurrency)
    return (
      <Tooltip>
        <TooltipTrigger
          render={
            <span
              tabIndex={0}
              aria-label={`${shown}, not converted — no exchange rate was available for this date`}
              className={cn(
                'cursor-help font-mono tabular-nums text-muted-foreground underline decoration-dotted underline-offset-4',
                className,
              )}
            />
          }
        >
          {shown}*
        </TooltipTrigger>
        <TooltipContent>
          Not converted — no exchange rate was available for this date.
        </TooltipContent>
      </Tooltip>
    )
  }

  if (!wasConverted(row)) {
    return (
      <span
        className={cn(
          'font-mono tabular-nums',
          tint && 'text-success',
          className,
        )}
      >
        {formatMoney(base ?? 0, row.base_currency)}
      </span>
    )
  }

  const shown = formatMoney(base ?? 0, row.base_currency)
  const summary = conversionSummary(row, posted, postedCurrency)
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            tabIndex={0}
            aria-label={`${shown}, converted from ${summary}`}
            className={cn(
              'cursor-help font-mono tabular-nums underline decoration-dotted underline-offset-4',
              tint && 'text-success',
              className,
            )}
          />
        }
      >
        {shown}
      </TooltipTrigger>
      <TooltipContent>{summary}</TooltipContent>
    </Tooltip>
  )
}
