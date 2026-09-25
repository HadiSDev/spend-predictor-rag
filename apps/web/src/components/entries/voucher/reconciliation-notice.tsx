import { TriangleAlert } from 'lucide-react'
import { formatMoney, toNumber } from '#/lib/format/format'
import type { InvoiceDetailRead } from '#/lib/api/types'

/** Warns when an invoice's lines no longer sum to its header. */
export function ReconciliationNotice({
  invoice,
}: {
  invoice: InvoiceDetailRead
}) {
  if (invoice.lines_reconciled || invoice.reconciliation_delta === null) {
    return null
  }

  const delta = toNumber(invoice.reconciliation_delta)
  const total = invoice.total === null ? null : toNumber(invoice.total)

  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/5 px-3 py-2"
    >
      <TriangleAlert
        className="mt-0.5 size-4 shrink-0 text-warning"
        aria-hidden="true"
      />
      <div className="text-sm">
        <p className="font-medium text-foreground">
          The lines do not add up to the invoice total.
        </p>
        <p className="text-muted-foreground">
          {total === null ? null : (
            <>
              Lines sum to{' '}
              <span className="tabular-nums text-foreground">
                {formatMoney(total + delta, invoice.currency)}
              </span>{' '}
              against a total of{' '}
              <span className="tabular-nums text-foreground">
                {formatMoney(total, invoice.currency)}
              </span>{' '}
            </>
          )}
          — {delta < 0 ? 'short by' : 'over by'}{' '}
          <span className="tabular-nums text-foreground">
            {formatMoney(Math.abs(delta), invoice.currency)}
          </span>
          .
        </p>
      </div>
    </div>
  )
}
