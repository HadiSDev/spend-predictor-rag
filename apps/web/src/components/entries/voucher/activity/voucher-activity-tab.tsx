import * as React from 'react'
import { Skeleton } from '#/components/ui'
import type { VoucherAuditRead } from '#/lib/api/types'
import { ActivityEvent } from './activity-event'
import { dayKey, dayLabel } from './activity-time'

const STAGGER_MS = 40

interface DayGroup {
  key: string
  label: string
  firstIndex: number
  rows: Array<VoucherAuditRead>
}

function groupByDay(rows: Array<VoucherAuditRead>): Array<DayGroup> {
  const groups: Array<DayGroup> = []
  rows.forEach((row, index) => {
    const key = dayKey(row.created_at)
    const current = groups.at(-1)
    if (current && current.key === key) {
      current.rows.push(row)
    } else {
      groups.push({
        key,
        label: dayLabel(row.created_at),
        firstIndex: index,
        rows: [row],
      })
    }
  })
  return groups
}

function usePrefersMotion(): boolean {
  const prefersMotion = React.useRef<boolean | null>(null)
  if (prefersMotion.current === null) {
    prefersMotion.current =
      typeof window === 'undefined' ||
      typeof window.matchMedia !== 'function' ||
      !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }
  return prefersMotion.current
}

function LoadingState() {
  return (
    <div className="flex flex-col gap-5">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex gap-3">
          <Skeleton className="size-8 shrink-0 rounded-full" />
          <div className="flex flex-1 flex-col gap-2 pt-1.5">
            <Skeleton className="h-4 w-2/3 rounded-md" />
            <Skeleton className="h-3 w-1/3 rounded-md" />
          </div>
        </div>
      ))}
    </div>
  )
}

export interface VoucherActivityTabProps {
  /** Newest first, as returned by the API. */
  rows: Array<VoucherAuditRead>
  loading: boolean
}

/** The Activity tab: the voucher's audit trail as a timeline, newest first. */
export function VoucherActivityTab({ rows, loading }: VoucherActivityTabProps) {
  const animate = usePrefersMotion()

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
    <div className="flex flex-col gap-6">
      {groupByDay(rows).map((group) => (
        <section key={group.key} aria-labelledby={`activity-day-${group.key}`}>
          <h3
            id={`activity-day-${group.key}`}
            className="mb-3 text-xs font-medium tracking-wide text-muted-foreground uppercase"
          >
            {group.label}
          </h3>
          <ol className="flex flex-col">
            {group.rows.map((row, index) => (
              <ActivityEvent
                key={row.id}
                row={row}
                animationDelayMs={
                  animate ? (group.firstIndex + index) * STAGGER_MS : undefined
                }
              />
            ))}
          </ol>
        </section>
      ))}
    </div>
  )
}
