import * as React from 'react'
import { Plus } from 'lucide-react'
import { Button } from '#/components/ui'
import { serverErrorMessage } from '#/lib/form-errors'
import type {
  InvoiceDetailRead,
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
  onVerifyLine: (lineId: string, corrections: LineCorrections) => Promise<void>
  onUpdateLine: (lineId: string, changes: InvoiceLineUpdate) => Promise<void>
  onCreateLine: (invoiceId: string) => Promise<void>
  onDeleteLine: (lineId: string) => Promise<void>
}

/**
 * The Lines tab: what was bought, the category assigned to each line, and the
 * two operations that change the invoice's line set.
 *
 * Its own tab rather than a section under Details, because the line is now the
 * unit this product works in — it is what the table lists, what a row opens
 * onto, and where a human's corrections land. Burying it under a header made it
 * the second thing on a tab about something else.
 *
 * A stand-in line is marked, and so is a hand-written one. Not disabled and not
 * tinted as a problem: both are real lines, categorizable and verifiable like
 * any other. The mark says only where the description came from — the
 * bookkeeper's memo, or a person who read the document — which is exactly what
 * a reader deciding whether to trust the category needs to know.
 */
export function VoucherLinesTab({
  invoice,
  spendTreeNodes,
  companySettingsHref,
  canManage,
  onVerifyLine,
  onUpdateLine,
  onCreateLine,
  onDeleteLine,
}: VoucherLinesTabProps) {
  const [adding, setAdding] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  async function handleAdd() {
    setAdding(true)
    setError(null)
    try {
      await onCreateLine(invoice.id)
    } catch (failure) {
      setError(serverErrorMessage(failure))
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <ReconciliationNotice invoice={invoice} />

      {invoice.lines.length === 0 ? (
        <p className="text-sm text-muted-foreground">No lines on this invoice.</p>
      ) : (
        invoice.lines.map((line) => (
          <div key={line.id} className="flex flex-col gap-1">
            {line.origin === 'entry_fallback' || line.origin === 'human' ? (
              <div className="self-start">
                <ProvenanceMark origin={line.origin} />
              </div>
            ) : null}
            <LineEditor
              line={line}
              currency={invoice.currency}
              nodes={spendTreeNodes}
              companySettingsHref={companySettingsHref}
              canManage={canManage}
              onVerify={onVerifyLine}
              onUpdate={onUpdateLine}
              onDelete={canManage ? onDeleteLine : undefined}
            />
          </div>
        ))
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
