import * as React from 'react'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { Button, cn } from '#/components/ui'
import { serverErrorMessage } from '#/lib/form-errors'
import type {
  InvoiceDetailRead,
  InvoiceLineRead,
  InvoiceLineUpdate,
  SpendCategoryRead,
} from '#/lib/api/types'
import { LineEditor } from '#/components/entries/lines/line-editor'
import type { LineCorrections } from '#/components/entries/lines/line-editor'
import { ReconciliationNotice } from './reconciliation-notice'
import { ProvenanceMark } from '#/components/entries/lines/provenance-mark'

export interface VoucherLinesTabProps {
  invoice: InvoiceDetailRead
  /** The company's spend tree, or null while loading. */
  spendTreeNodes: Array<SpendCategoryRead> | null
  companySettingsHref?: string
  /** Whether the reader may write. */
  canManage: boolean
  /** The line to show first. */
  initialLineId?: string | null
  onVerifyLine: (lineId: string, corrections: LineCorrections) => Promise<void>
  onUpdateLine: (lineId: string, changes: InvoiceLineUpdate) => Promise<void>
  onCreateLine: (invoiceId: string) => Promise<void>
  onDeleteLine: (lineId: string) => Promise<void>
}

/** Orders lines by their source position, then id. */
function inDocumentOrder(
  lines: Array<InvoiceLineRead>,
): Array<InvoiceLineRead> {
  return [...lines].sort(
    (a, b) =>
      a.sequence - b.sequence || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  )
}

/** Which way the reader moved. */
type Direction = 'next' | 'prev'

/** The Lines tab: one invoice line at a time, with its category. */
export function VoucherLinesTab({
  invoice,
  spendTreeNodes,
  companySettingsHref,
  canManage,
  initialLineId,
  onVerifyLine,
  onUpdateLine,
  onCreateLine,
  onDeleteLine,
}: VoucherLinesTabProps) {
  const [adding, setAdding] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const lines = React.useMemo(
    () => inDocumentOrder(invoice.lines),
    [invoice.lines],
  )

  const [index, setIndex] = React.useState(0)
  const [direction, setDirection] = React.useState<Direction>('next')
  const [dirty, setDirty] = React.useState(false)
  /** A step waiting on the reviewer's answer about unsaved work. */
  const [pending, setPending] = React.useState<{
    to: number
    how: Direction
  } | null>(null)

  React.useEffect(() => {
    if (!initialLineId) {
      return
    }
    const found = lines.findIndex((line) => line.id === initialLineId)
    if (found >= 0) {
      setIndex(found)
    }
  }, [initialLineId, lines])

  const position = Math.min(index, Math.max(0, lines.length - 1))
  const current: InvoiceLineRead | undefined = lines[position]
  const hasPrev = position > 0
  const hasNext = position < lines.length - 1

  function move(to: number, how: Direction) {
    setDirection(how)
    setIndex(to)
    setPending(null)
  }

  /** Step, unless the card has unsaved work. */
  function step(how: Direction) {
    const to = how === 'next' ? position + 1 : position - 1
    if (to < 0 || to > lines.length - 1) {
      return
    }
    if (dirty) {
      setPending({ to, how })
      return
    }
    move(to, how)
  }

  /** Pages with the arrow keys when focus is outside a text-entry control. */
  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') {
      return
    }
    const target = event.target as HTMLElement | null
    const tag = target?.tagName
    if (
      tag === 'INPUT' ||
      tag === 'TEXTAREA' ||
      tag === 'SELECT' ||
      target?.isContentEditable
    ) {
      return
    }
    event.preventDefault()
    step(event.key === 'ArrowRight' ? 'next' : 'prev')
  }

  async function handleAdd() {
    setAdding(true)
    setError(null)
    try {
      await onCreateLine(invoice.id)
      move(lines.length, 'next')
    } catch (failure) {
      setError(serverErrorMessage(failure))
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="flex flex-col gap-3" onKeyDown={handleKeyDown}>
      <ReconciliationNotice invoice={invoice} />

      {lines.length === 0 || current === undefined ? (
        <p className="text-sm text-muted-foreground">
          No lines on this invoice.
        </p>
      ) : (
        <>
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs tabular-nums text-muted-foreground">
                {position + 1} of {lines.length}
              </span>
              {current.origin === 'entry_fallback' ||
              current.origin === 'human' ? (
                <ProvenanceMark origin={current.origin} />
              ) : null}
            </div>
            <div className="flex items-center gap-1">
              <Button
                size="sm"
                variant="outline"
                aria-label="Previous line"
                disabled={!hasPrev}
                onClick={() => step('prev')}
              >
                <ChevronLeft aria-hidden="true" />
                Previous
              </Button>
              <Button
                size="sm"
                variant="outline"
                aria-label="Next line"
                disabled={!hasNext}
                onClick={() => step('next')}
              >
                Next
                <ChevronRight aria-hidden="true" />
              </Button>
            </div>
          </div>

          {pending !== null ? (
            <div className="flex flex-col gap-2 rounded-md border border-border bg-muted/40 p-3">
              <p className="text-sm">
                This line has unsaved changes. Leaving it will discard them.
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => move(pending.to, pending.how)}
                >
                  Discard and continue
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setPending(null)}
                >
                  Stay on this line
                </Button>
              </div>
            </div>
          ) : null}

          <div
            key={current.id}
            className={cn(
              direction === 'next' ? 'ep-line-next' : 'ep-line-prev',
            )}
          >
            <LineEditor
              line={current}
              currency={invoice.currency}
              nodes={spendTreeNodes}
              companySettingsHref={companySettingsHref}
              canManage={canManage}
              onVerify={onVerifyLine}
              onUpdate={onUpdateLine}
              onDelete={canManage ? onDeleteLine : undefined}
              onDirtyChange={setDirty}
            />
          </div>
        </>
      )}

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {canManage ? (
        <Button
          size="sm"
          variant="outline"
          className="self-start"
          disabled={adding}
          onClick={() => void handleAdd()}
        >
          <Plus aria-hidden="true" />
          {adding ? 'Adding…' : 'Add line'}
        </Button>
      ) : null}
    </div>
  )
}
