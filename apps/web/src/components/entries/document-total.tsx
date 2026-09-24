import { FileText } from 'lucide-react'
import { formatMoney } from '#/lib/format'
import type { InvoiceDetailRead } from '#/lib/types'

/**
 * Says what the *supplier's document* billed, when it differs from what the
 * bookkeeper posted.
 *
 * Only then. A second figure that always matches teaches the reader to stop
 * looking at it, and by the time it does differ they no longer are.
 *
 * The two disagreeing is a finding, not an error: a partial posting, a credit
 * note applied on one side, or a plain typo are all real and all things a human
 * resolves — beside the scan, which this panel already shows. It is deliberately
 * *not* a warning: the extraction was accepted precisely because the document
 * adds up against its own totals block, and the server has already excused the
 * ordinary gross-versus-net case, so what is left is worth a reader's attention
 * rather than an alarm.
 *
 * Nothing is rendered when the document stated no total. `totals_agree` is null
 * there rather than true, so "nothing to compare" never reads as "compared and
 * agreed".
 */
export function DocumentTotal({ invoice }: { invoice: InvoiceDetailRead }) {
  if (invoice.totals_agree !== false || invoice.document_total === null) return null

  return (
    <div
      role="note"
      className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-3 py-2"
    >
      <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <p className="text-sm text-muted-foreground">
        The document states a total of{' '}
        <span className="font-medium tabular-nums text-foreground">
          {formatMoney(invoice.document_total, invoice.currency)}
        </span>
        {invoice.document_tax === null ? null : (
          <>
            {' '}
            (VAT{' '}
            <span className="tabular-nums text-foreground">
              {formatMoney(invoice.document_tax, invoice.currency)}
            </span>
            )
          </>
        )}
        , where the ledger posted{' '}
        <span className="font-medium tabular-nums text-foreground">
          {invoice.total === null ? '—' : formatMoney(invoice.total, invoice.currency)}
        </span>
        .
      </p>
    </div>
  )
}
