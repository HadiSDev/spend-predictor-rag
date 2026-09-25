import * as React from 'react'
import { RefreshCw } from 'lucide-react'
import { Badge, Button } from '#/components/ui'
import type { DocStatus, InvoiceDetailRead } from '#/lib/api/types'

/** Reader-facing description of each processing state. */
const DESCRIPTIONS: Record<DocStatus, string> = {
  not_applicable:
    'No document is attached to this voucher, so its lines stand in for its postings.',
  pending:
    'Waiting to be read. Its lines will be replaced once the document has been processed.',
  processing: 'Being read right now.',
  processed: 'Read — the lines below came from the document.',
  failed: 'Could not be read. Its lines still stand in for its postings.',
}

const VARIANTS: Record<
  DocStatus,
  'outline' | 'info' | 'success' | 'destructive'
> = {
  not_applicable: 'outline',
  pending: 'info',
  processing: 'info',
  processed: 'success',
  failed: 'destructive',
}

const LABELS: Record<DocStatus, string> = {
  not_applicable: 'No document',
  pending: 'Queued',
  processing: 'Processing',
  processed: 'Processed',
  failed: 'Failed',
}

export interface DocumentProcessingProps {
  invoice: InvoiceDetailRead
  /** Whether the signed-in user may retrigger processing. */
  canRetrigger: boolean
  onReprocess: (invoiceId: string) => Promise<void>
}

/** Document processing state for a voucher, with a reprocess action. */
export function DocumentProcessing({
  invoice,
  canRetrigger,
  onReprocess,
}: DocumentProcessingProps) {
  const [busy, setBusy] = React.useState(false)
  const status = invoice.doc_status

  const actionable =
    canRetrigger && invoice.has_document && status !== 'processing'

  async function handleReprocess() {
    setBusy(true)
    try {
      await onReprocess(invoice.id)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">Document</h3>
        <Badge variant={VARIANTS[status]}>{LABELS[status]}</Badge>
      </div>
      <p className="text-sm text-muted-foreground">{DESCRIPTIONS[status]}</p>
      {invoice.doc_error ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-muted-foreground">
          {invoice.doc_error}
        </p>
      ) : null}
      {actionable ? (
        <Button
          variant="secondary"
          size="sm"
          className="self-start"
          disabled={busy}
          onClick={handleReprocess}
        >
          <RefreshCw aria-hidden="true" />
          {busy ? 'Queueing…' : 'Process document again'}
        </Button>
      ) : null}
    </section>
  )
}
