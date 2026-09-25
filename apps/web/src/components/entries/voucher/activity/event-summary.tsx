import * as React from 'react'
import { ArrowRight, ChevronRight } from 'lucide-react'
import { Badge, cn } from '#/components/ui'
import {
  LINE_STATUS_LABEL,
  lineStatusVariant,
} from '#/components/entries/lines/line-status'
import {
  DOC_STATUS_LABEL,
  DOC_STATUS_VARIANT,
} from '#/components/entries/invoice-document/document-processing'
import type { DocStatus } from '#/lib/api/types'
import type { SummaryItem } from './describe-event'

const LOW_CONFIDENCE_PERCENT = 70
const NOTE_PREVIEW_LENGTH = 220

type ItemOf<TKind extends SummaryItem['kind']> = Extract<
  SummaryItem,
  { kind: TKind }
>

function CategoryPath({
  levels,
  muted,
}: {
  levels: Array<string>
  muted?: boolean
}) {
  return (
    <span
      className={cn(
        'inline-flex flex-wrap items-center gap-1',
        muted ? 'text-muted-foreground line-through' : 'text-foreground',
      )}
    >
      {levels.map((level, index) => (
        <React.Fragment key={`${index}-${level}`}>
          {index > 0 ? (
            <ChevronRight
              className="size-3 text-muted-foreground"
              aria-hidden
            />
          ) : null}
          <span
            className={
              index === levels.length - 1 && !muted ? 'font-medium' : undefined
            }
          >
            {level}
          </span>
        </React.Fragment>
      ))}
    </span>
  )
}

function CategoryChange({ item }: { item: ItemOf<'category'> }) {
  if (!item.after) {
    return <p className="text-xs text-muted-foreground">Category cleared</p>
  }
  return (
    <div className="flex flex-col gap-1 text-sm">
      {item.before ? <CategoryPath levels={item.before} muted /> : null}
      <CategoryPath levels={item.after} />
    </div>
  )
}

function Transition({
  before,
  after,
}: {
  before: React.ReactNode
  after: React.ReactNode
}) {
  return (
    <span className="inline-flex items-center gap-1">
      {before}
      {before ? (
        <ArrowRight className="size-3 text-muted-foreground" aria-label="to" />
      ) : null}
      {after}
    </span>
  )
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) {
    return null
  }
  return (
    <Badge variant={lineStatusVariant(status)}>
      {LINE_STATUS_LABEL[status] ?? status}
    </Badge>
  )
}

function DocumentStatusBadge({ status }: { status: string | null }) {
  if (!status) {
    return null
  }
  const known = status in DOC_STATUS_LABEL ? (status as DocStatus) : null
  return (
    <Badge variant={known ? DOC_STATUS_VARIANT[known] : 'default'}>
      {known ? DOC_STATUS_LABEL[known] : status}
    </Badge>
  )
}

function Facts({ items }: { items: Array<SummaryItem> }) {
  const facts = items.flatMap((item) => {
    if (item.kind === 'status') {
      return [
        <Transition
          key="status"
          before={<StatusBadge status={item.before} />}
          after={<StatusBadge status={item.after} />}
        />,
      ]
    }
    if (item.kind === 'document-status') {
      return [
        <Transition
          key="document-status"
          before={<DocumentStatusBadge status={item.before} />}
          after={<DocumentStatusBadge status={item.after} />}
        />,
      ]
    }
    if (item.kind === 'account' && item.after) {
      return [
        <Badge key="account" variant="outline" className="tabular-nums">
          {item.after}
        </Badge>,
      ]
    }
    if (item.kind === 'confidence') {
      return [
        <Badge
          key="confidence"
          variant={
            item.percent < LOW_CONFIDENCE_PERCENT ? 'warning' : 'outline'
          }
        >
          {item.percent}% confidence
        </Badge>,
      ]
    }
    return []
  })

  if (facts.length === 0) {
    return null
  }
  return <div className="flex flex-wrap items-center gap-1.5">{facts}</div>
}

function FieldChanges({ items }: { items: Array<ItemOf<'field'>> }) {
  if (items.length === 0) {
    return null
  }
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
      {items.map((item) => (
        <React.Fragment key={item.label}>
          <dt className="text-muted-foreground">{item.label}</dt>
          <dd className="min-w-0">
            <span className="text-muted-foreground line-through">
              {item.before}
            </span>
            <ArrowRight
              className="mx-1 inline size-3 text-muted-foreground"
              aria-label="to"
            />
            <span className="font-medium text-foreground">{item.after}</span>
          </dd>
        </React.Fragment>
      ))}
    </dl>
  )
}

function Note({ item }: { item: ItemOf<'note'> }) {
  const [expanded, setExpanded] = React.useState(false)
  const long = item.text.length > NOTE_PREVIEW_LENGTH
  return (
    <figure
      className={cn(
        'border-l-2 pl-3',
        item.tone === 'destructive' ? 'border-destructive/50' : 'border-border',
      )}
    >
      <figcaption
        className={cn(
          'text-[11px] font-medium tracking-wide uppercase',
          item.tone === 'destructive'
            ? 'text-destructive'
            : 'text-muted-foreground',
        )}
      >
        {item.label}
      </figcaption>
      <blockquote
        className={cn(
          'mt-0.5 text-xs leading-relaxed text-muted-foreground',
          long && !expanded ? 'line-clamp-3' : undefined,
        )}
      >
        {item.text}
      </blockquote>
      {long ? (
        <button
          type="button"
          className="mt-1 text-xs font-medium text-foreground underline-offset-2 hover:underline"
          aria-expanded={expanded}
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      ) : null}
    </figure>
  )
}

/** What an audit event changed, laid out by meaning rather than by field. */
export function EventSummary({ items }: { items: Array<SummaryItem> }) {
  if (items.length === 0) {
    return null
  }
  const category = items.find(
    (item): item is ItemOf<'category'> => item.kind === 'category',
  )
  const fields = items.filter(
    (item): item is ItemOf<'field'> => item.kind === 'field',
  )
  const notes = items.filter(
    (item): item is ItemOf<'note'> => item.kind === 'note',
  )

  return (
    <div className="mt-2 flex flex-col gap-2">
      {category ? <CategoryChange item={category} /> : null}
      <Facts items={items} />
      <FieldChanges items={fields} />
      {notes.map((note) => (
        <Note key={note.label} item={note} />
      ))}
    </div>
  )
}
