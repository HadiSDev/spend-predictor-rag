import { TriangleAlert } from 'lucide-react'
import { formatMoney, toNumber } from '#/lib/format'
import type { InvoiceDetailRead } from '#/lib/types'

/**
 * Says so when an invoice's lines no longer sum to its header.
 *
 * A warning, never a block. A reviewer splitting a stand-in line works
 * incrementally — add, add, delete — and every intermediate step is out of
 * balance; refusing the save would make the operation impossible to perform one
 * field at a time. The ERP's own total may also be the wrong figure, and this
 * is how a reviewer notices that.
 *
 * Both figures and the signed difference, because "the lines are 400 short" and
 * "the lines are 400 over" call for opposite corrections, and a bare "does not
 * reconcile" leaves the reader to do the subtraction.
 */
export function ReconciliationNotice({ invoice }: { invoice: InvoiceDetailRead }) {
  if (invoice.lines_reconciled || invoice.reconciliation_delta === null) return null

  const delta = toNumber(invoice.reconciliation_delta)
  // Null only in the case the server never reports a delta for (no total means
  // nothing to reconcile against), but narrowed here so the figures below can
  // be rendered without a non-null assertion.
  const total = invoice.total === null ? null : toNumber(invoice.total)

  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/5 px-3 py-2"
    >
      <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
      <div className="text-sm">
        <p className="font-medium text-foreground">The lines do not add up to the invoice total.</p>
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
          {/* Signed, and spelled out in words as well: a leading minus is easy
              to miss on a number that already has a currency in front of it. */}
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
