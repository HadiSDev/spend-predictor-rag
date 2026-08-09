import * as React from 'react'
import { RefreshCw } from 'lucide-react'
import { Badge, Button } from '#/components/ui'
import type { DocStatus, InvoiceDetailRead } from '#/lib/types'

/** What each processing state means, in the reader's terms rather than ours. */
const DESCRIPTIONS: Record<DocStatus, string> = {
  // Not a failure: most vouchers arrive without a scan, and their lines stand
  // in for the postings, which is a correct if coarse answer.
  not_applicable: 'No document is attached to this voucher, so its lines stand in for its postings.',
  pending: 'Waiting to be read. Its lines will be replaced once the document has been processed.',
  processing: 'Being read right now.',
  processed: 'Read — the lines below came from the document.',
  failed: 'Could not be read. Its lines still stand in for its postings.',
}

const VARIANTS: Record<DocStatus, 'outline' | 'info' | 'success' | 'destructive'> = {
  // Outline, not a tinted state: a voucher with no scan is the ordinary case,
  // and colouring it would flag most of the ledger as though something were
  // wrong.
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
  /** Whether the signed-in user may retrigger — the endpoint is management-only,
   *  so a read-only member is shown the state without the action. */
  canRetrigger: boolean
  onReprocess: (invoiceId: string) => Promise<void>
}

/**
 * Whether this voucher's document has been read, and the way to ask again.
 *
 * The action is offered only where the API will accept it: an invoice with a
 * document that is not currently being processed, for a user with a management
 * role. Offering a control that answers 409 teaches the reader to distrust the
 * screen, and a *disabled* control claims a permission that will never be
 * granted — so where the action does not apply there is simply no control.
 */
export function DocumentProcessing({
  invoice,
  canRetrigger,
  onReprocess,
}: DocumentProcessingProps) {
  const [busy, setBusy] = React.useState(false)
  const status = invoice.doc_status

  // Exactly the conditions `POST /invoices/{id}/reprocess` enforces.
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
      {/* The reason, in the words the API returned — the reader is not asked to
          retry blind. */}
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
