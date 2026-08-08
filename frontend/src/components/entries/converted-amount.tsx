import { Tooltip, TooltipContent, TooltipTrigger, cn } from '#/components/ui'
import { formatMoney, toNumber } from '#/lib/format'
import type { Converted, Money } from '#/lib/types'

const rateDateFormatter = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' })

function formatRateDate(value: string | null): string {
  if (!value) return 'an unknown date'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : rateDateFormatter.format(parsed)
}

/** A rate of exactly 1 is a same-currency row, not a conversion worth explaining. */
export function wasConverted(row: Converted): boolean {
  return row.base_currency !== null && row.fx_rate !== null && toNumber(row.fx_rate) !== 1
}

/**
 * How a converted figure explains itself: the amount as posted, the rate, and
 * the date that rate was published for.
 */
export function conversionSummary(
  row: Converted,
  posted: Money | null,
  postedCurrency: string | null,
): string {
  const original = formatMoney(posted ?? 0, postedCurrency)
  const rate = row.fx_rate === null ? '?' : toNumber(row.fx_rate).toLocaleString('en-GB', {
    maximumFractionDigits: 6,
  })
  return `${original} at ${rate} ${row.base_currency}/${postedCurrency}, rate of ${formatRateDate(row.fx_rate_date)}`
}

export interface ConvertedAmountProps {
  /** The row's conversion: base currency, rate, and the rate's publication date. */
  row: Converted
  /** The figure in the base currency. Null means the row was not converted. */
  base: Money | null
  /** The same figure exactly as the ERP posted it — always shown as evidence. */
  posted: Money | null
  postedCurrency: string | null
  className?: string
  /** Tint negative figures, which mean spend was reduced rather than incurred. */
  signed?: boolean
}

/**
 * One monetary figure in the company's own currency, able to account for itself.
 *
 * Three cases, and the distinction between them is the point:
 * - **converted** — shows the base amount; hover *or focus* reveals what was
 *   posted and the rate that got it here.
 * - **posted in the base currency** — nothing to explain, so no disclosure. A
 *   rate of 1 dressed up as a conversion would be noise.
 * - **unconverted** — shows the posted amount in its own currency, marked, so
 *   the money is visible rather than rendered as a `0.00` in a currency it is
 *   not in.
 */
export function ConvertedAmount({
  row,
  base,
  posted,
  postedCurrency,
  className,
  signed = false,
}: ConvertedAmountProps) {
  const tint = signed && base !== null && toNumber(base) < 0

  if (row.base_currency === null) {
    const shown = formatMoney(posted ?? 0, postedCurrency)
    return (
      <Tooltip>
        <TooltipTrigger
          render={
            <span
              tabIndex={0}
              // The explanation lives in the accessible name as well as the
              // tooltip: a screen-reader user cannot hover, and an amount that
              // only explains itself to a mouse explains itself to nobody.
              aria-label={`${shown}, not converted — no exchange rate was available for this date`}
              className={cn(
                'cursor-help tabular-nums text-muted-foreground underline decoration-dotted underline-offset-4',
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
      <span className={cn('tabular-nums', tint && 'text-success', className)}>
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
              'cursor-help tabular-nums underline decoration-dotted underline-offset-4',
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
