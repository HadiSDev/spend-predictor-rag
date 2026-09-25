import { FileText } from 'lucide-react'
import { formatMoney } from '#/lib/format/format'
import type { InvoiceDetailRead } from '#/lib/api/types'

/** Note showing the document's stated total when it differs from the posted total. */
export function DocumentTotal({ invoice }: { invoice: InvoiceDetailRead }) {
  if (invoice.totals_agree !== false || invoice.document_total === null) {
    return null
  }

  return (
    <div
      role="note"
      className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-3 py-2"
    >
      <FileText
        className="mt-0.5 size-4 shrink-0 text-muted-foreground"
        aria-hidden="true"
      />
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
          {invoice.total === null
            ? '—'
            : formatMoney(invoice.total, invoice.currency)}
        </span>
        .
      </p>
    </div>
  )
}
