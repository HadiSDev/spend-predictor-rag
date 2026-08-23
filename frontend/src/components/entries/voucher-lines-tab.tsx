import * as React from 'react'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { Button, cn } from '#/components/ui'
import { serverErrorMessage } from '#/lib/form-errors'
import type {
  InvoiceDetailRead,
  InvoiceLineRead,
  InvoiceLineUpdate,
  SpendCategoryRead,
} from '#/lib/types'
import { LineEditor } from './line-editor'
import type { LineCorrections } from './line-editor'
import { ReconciliationNotice } from './reconciliation-notice'
import { ProvenanceMark } from './voucher-table'

export interface VoucherLinesTabProps {
  invoice: InvoiceDetailRead
  /** The company's spend tree, flat and shallowest-first. Null while loading;
   *  empty when no tree is assigned. Passed down rather than fetched here so
   *  one request serves every line on the voucher. */
  spendTreeNodes: Array<SpendCategoryRead> | null
  companySettingsHref?: string
  /** Whether the reader may write. Every action on this tab is
   *  management-gated server-side. */
  canManage: boolean
  /** The line the reader activated in the table, if they opened the panel from
   *  one. Seeds which line is shown; the tab owns the position from then on. */
  initialLineId?: string | null
  onVerifyLine: (lineId: string, corrections: LineCorrections) => Promise<void>
  onUpdateLine: (lineId: string, changes: InvoiceLineUpdate) => Promise<void>
  onCreateLine: (invoiceId: string) => Promise<void>
  onDeleteLine: (lineId: string) => Promise<void>
}

/**
 * The order a document is read in: the position each line's source stated,
 * with the id as a tiebreak.
 *
 * The row id is a random UUID, so sorting by it alone scrambles an invoice —
 * invisible while every line was on screen at once, and wrong the moment they
 * are shown one at a time, because "next" would mean nothing.
 */
function inDocumentOrder(lines: Array<InvoiceLineRead>): Array<InvoiceLineRead> {
  return [...lines].sort(
    (a, b) => a.sequence - b.sequence || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  )
}

/** Which way the reader moved, so the card can enter from that side. */
type Direction = 'next' | 'prev'

/**
 * The Lines tab: what was bought, the category assigned to each line, and the
 * two operations that change the invoice's line set.
 *
 * **One line at a time.** A stacked list turned a six-line invoice into a
 * scroll, with the line a reader actually came to correct somewhere below the
 * fold. Exactly one card is *mounted* — not merely shown — because hidden
 * siblings keep their inputs focusable and their unsaved state alive, so Tab
 * walks into an invisible line's amount field and "does this card have unsaved
 * work?" stops having a single answer.
 *
 * A stand-in line is marked, and so is a hand-written one. Not disabled and not
 * tinted as a problem: both are real lines, categorizable and verifiable like
 * any other. The mark says only where the text came from — the bookkeeper's
 * memo, or a person who read the document — which is exactly what a reader
 * deciding whether to trust the category needs to know.
 */
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

  const lines = React.useMemo(() => inDocumentOrder(invoice.lines), [invoice.lines])

  const [index, setIndex] = React.useState(0)
  const [direction, setDirection] = React.useState<Direction>('next')
  const [dirty, setDirty] = React.useState(false)
  /** A step waiting on the reviewer's answer about unsaved work. */
  const [pending, setPending] = React.useState<{ to: number; how: Direction } | null>(null)

  // Open on the line the reader activated. An effect rather than a `useState`
  // initializer because the panel stays mounted while the selection changes —
  // activating a different line must move the card, not be ignored because the
  // component happened to already exist.
  React.useEffect(() => {
    if (!initialLineId) return
    const found = lines.findIndex((line) => line.id === initialLineId)
    if (found >= 0) setIndex(found)
  }, [initialLineId, lines])

  // Deleting the last line would otherwise strand the index past the end.
  const position = Math.min(index, Math.max(0, lines.length - 1))
  // Typed as possibly absent on purpose: indexing an array yields `T` under this
  // tsconfig, so without the annotation the empty-invoice guard below reads to
  // the compiler as dead code — and would be deleted by someone tidying up.
  const current: InvoiceLineRead | undefined = lines[position]
  const hasPrev = position > 0
  const hasNext = position < lines.length - 1

  function move(to: number, how: Direction) {
    setDirection(how)
    setIndex(to)
    setPending(null)
  }

  /**
   * Step, unless the card has unsaved work.
   *
   * Prompting only when genuinely dirty is what keeps this usable: a
   * confirmation on every step would make paging a ten-line invoice ten
   * dialogs. `dirty` compares *parsed* values, so the formatter rewriting
   * `1234.50000` as `1,234.50` on mount does not count as an edit.
   */
  function step(how: Direction) {
    const to = how === 'next' ? position + 1 : position - 1
    if (to < 0 || to > lines.length - 1) return
    if (dirty) {
      setPending({ to, how })
      return
    }
    move(to, how)
  }

  /**
   * Arrow keys page — but only when focus is outside a text-entry control,
   * where an arrow already means "move the caret". Stealing it there would make
   * every numeric field impossible to edit.
   */
  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    const target = event.target as HTMLElement | null
    const tag = target?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable) {
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
      // A new line is appended, and it is what the reviewer wants to fill in.
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
        <p className="text-sm text-muted-foreground">No lines on this invoice.</p>
      ) : (
        <>
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {/* Position first, because "which of how many" is the question a
                  reader has the moment the list stops being visible. */}
              <span className="text-xs tabular-nums text-muted-foreground">
                {position + 1} of {lines.length}
              </span>
              {current.origin === 'entry_fallback' || current.origin === 'human' ? (
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
                <Button size="sm" variant="outline" onClick={() => move(pending.to, pending.how)}>
                  Discard and continue
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setPending(null)}>
                  Stay on this line
                </Button>
              </div>
            </div>
          ) : null}

          {/*
            `key` is the line id, so React replaces the card rather than reusing
            it — which restarts the entry animation and, more importantly, gives
            the editor a fresh state for the new line instead of carrying the
            previous one's pending edits into it.
          */}
          <div
            key={current.id}
            className={cn(direction === 'next' ? 'ep-line-next' : 'ep-line-prev')}
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
        // An empty line the reviewer then fills in, rather than a form to
        // complete first: splitting a stand-in is add, add, delete, and a modal
        // per line would put three dialogs in the way of one operation.
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
