import * as React from 'react'
import { Skeleton } from '#/components/ui'
import type { VoucherAuditRead } from '#/lib/api/types'

const dateTimeFormatter = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium',
  timeStyle: 'short',
})
const relativeFormatter = new Intl.RelativeTimeFormat('en-GB', {
  numeric: 'auto',
})

const DIVISIONS: Array<{ amount: number; unit: Intl.RelativeTimeFormatUnit }> =
  [
    { amount: 60, unit: 'seconds' },
    { amount: 60, unit: 'minutes' },
    { amount: 24, unit: 'hours' },
    { amount: 7, unit: 'days' },
    { amount: 4.34524, unit: 'weeks' },
    { amount: 12, unit: 'months' },
    { amount: Number.POSITIVE_INFINITY, unit: 'years' },
  ]

/** A relative time such as "3 hours ago", or the raw string if unparseable. */
function formatRelative(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  let duration = (parsed.getTime() - Date.now()) / 1000
  for (const division of DIVISIONS) {
    if (Math.abs(duration) < division.amount) {
      return relativeFormatter.format(Math.round(duration), division.unit)
    }
    duration /= division.amount
  }
  return relativeFormatter.format(Math.round(duration), 'years')
}

function formatAbsolute(value: string): string | undefined {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? undefined
    : dateTimeFormatter.format(parsed)
}

/** A changed value for display, with empty values shown as "—". */
function formatChangeValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  return typeof value === 'string' ? value : JSON.stringify(value)
}

function AuditTimestamp({ value }: { value: string }) {
  const absolute = formatAbsolute(value)
  return (
    <time
      dateTime={value}
      title={absolute}
      className="shrink-0 text-xs whitespace-nowrap text-muted-foreground"
    >
      {formatRelative(value)}
    </time>
  )
}

/** The field-level changes of one audit row. */
function ChangeList({ changes }: { changes: VoucherAuditRead['changes'] }) {
  if (!changes || changes.length === 0) {
    return null
  }
  return (
    <dl className="mt-1.5 flex flex-col gap-0.5 text-xs text-muted-foreground">
      {changes.map((change) => (
        <div key={change.field} className="flex gap-1">
          <dt className="font-medium text-foreground">{change.field}:</dt>
          <dd>
            {formatChangeValue(change.old)} → {formatChangeValue(change.new)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function AuditItem({
  row,
  index,
  animate,
}: {
  row: VoucherAuditRead
  index: number
  animate: boolean
}) {
  const actor = row.actor === 'system' || !row.actor ? 'system' : row.actor
  return (
    <li
      className={animate ? 'ep-activity-row' : undefined}
      style={animate ? { animationDelay: `${index * 40}ms` } : undefined}
    >
      <div className="flex items-start justify-between gap-3 border-b border-border py-3 last:border-b-0">
        <div className="min-w-0">
          <p className="text-sm">
            <span className="font-medium">{actor}</span>{' '}
            <span className="text-muted-foreground">{row.action}</span>{' '}
            <span className="font-medium">{row.entity_label}</span>
          </p>
          <ChangeList changes={row.changes} />
        </div>
        <AuditTimestamp value={row.created_at} />
      </div>
    </li>
  )
}

function LoadingState() {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-12 rounded-md" />
      ))}
    </div>
  )
}

export interface VoucherActivityTabProps {
  /** Newest first, as returned by the API. */
  rows: Array<VoucherAuditRead>
  loading: boolean
}

/** The Activity tab: the voucher's audit trail, newest first. */
export function VoucherActivityTab({ rows, loading }: VoucherActivityTabProps) {
  const animateRef = React.useRef<boolean | null>(null)
  if (animateRef.current === null) {
    animateRef.current =
      typeof window === 'undefined' ||
      typeof window.matchMedia !== 'function' ||
      !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }
  const animate = animateRef.current

  if (loading) {
    return <LoadingState />
  }

  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No changes recorded for this voucher yet.
      </p>
    )
  }

  return (
    <ul className="flex flex-col">
      {rows.map((row, index) => (
        <AuditItem key={row.id} row={row} index={index} animate={animate} />
      ))}
    </ul>
  )
}
