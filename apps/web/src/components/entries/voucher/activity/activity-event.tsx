import { cn } from '#/components/ui'
import type { VoucherAuditRead } from '#/lib/api/types'
import { fullDateTime, timeOfDay } from './activity-time'
import { describeEvent } from './describe-event'
import type { EventDescription, EventTone } from './describe-event'
import { EventSummary } from './event-summary'

const MARKER_TONE: Record<EventTone, string> = {
  ai: 'bg-primary text-primary-foreground',
  failure: 'bg-destructive/12 text-destructive ring-1 ring-destructive/30',
  person: 'bg-card text-foreground ring-1 ring-border',
  system: 'bg-muted text-muted-foreground',
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts
  return letters.map((part) => part.charAt(0).toUpperCase()).join('')
}

function EventMarker({ event }: { event: EventDescription }) {
  const Icon = event.icon
  if (event.tone === 'person') {
    return (
      <span
        aria-hidden
        className={cn(
          'relative grid size-8 shrink-0 place-items-center rounded-full text-[11px] font-semibold',
          MARKER_TONE.person,
        )}
      >
        {initials(event.actorName)}
        <span className="absolute -right-1 -bottom-1 grid size-4 place-items-center rounded-full bg-background ring-1 ring-border">
          <Icon className="size-2.5" />
        </span>
      </span>
    )
  }
  return (
    <span
      aria-hidden
      className={cn(
        'grid size-8 shrink-0 place-items-center rounded-full',
        MARKER_TONE[event.tone],
      )}
    >
      <Icon className="size-4" />
    </span>
  )
}

export interface ActivityEventProps {
  row: VoucherAuditRead
  animationDelayMs?: number
}

/** One audit event on the timeline: who did what, then what it changed. */
export function ActivityEvent({ row, animationDelayMs }: ActivityEventProps) {
  const event = describeEvent(row)
  const animated = animationDelayMs !== undefined
  return (
    <li
      className={cn(
        'group relative flex gap-3 pb-6 last:pb-0',
        animated && 'ep-activity-row',
      )}
      style={animated ? { animationDelay: `${animationDelayMs}ms` } : undefined}
    >
      <span
        aria-hidden
        className="absolute top-9 bottom-1 left-4 w-px bg-border group-last:hidden"
      />
      <EventMarker event={event} />
      <div className="min-w-0 flex-1 pt-1.5">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-sm leading-snug">
            {event.headline.map((part, index) =>
              part.strong ? (
                <span key={index} className="font-semibold">
                  {part.text}
                </span>
              ) : (
                <span key={index} className="text-muted-foreground">
                  {part.text}
                </span>
              ),
            )}
          </p>
          <time
            dateTime={row.created_at}
            title={fullDateTime(row.created_at)}
            className="shrink-0 text-xs whitespace-nowrap text-muted-foreground tabular-nums"
          >
            {timeOfDay(row.created_at)}
          </time>
        </div>
        <EventSummary items={event.summary} />
      </div>
    </li>
  )
}
