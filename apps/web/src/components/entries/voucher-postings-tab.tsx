import * as React from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Badge, cn } from '#/components/ui'
import { postingAmount } from '#/lib/entry-amount'
import { formatMoney, toNumber } from '#/lib/format'
import type { ErpEntryRead } from '#/lib/types'
import { wasConverted } from './converted-amount'

/**
 * A labelled field in a posting's detail, used throughout this tab so every
 * field is laid out identically.
 */
export function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-3 py-2 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

export function Value({ children }: { children: React.ReactNode }) {
  return children === null || children === undefined || children === '' ? (
    <span className="text-muted-foreground">—</span>
  ) : (
    <>{children}</>
  )
}

/**
 * The conversion, spelled out rather than tucked into a tooltip.
 *
 * The drawer is where someone goes to check a figure, so the rate and the date
 * it was published for are labelled fields here — a hover disclosure is fine on
 * a dense table, but not where the question being asked is "why this number?".
 *
 * A posting already in the company's currency shows nothing: a rate of 1 is not
 * a conversion, and presenting it as one would invite doubt where there is none.
 */
export function ConversionRows({ entry }: { entry: ErpEntryRead }) {
  if (entry.base_currency === null) {
    return (
      <Row label="Converted">
        <span className="text-muted-foreground">
          Not converted — no exchange rate was available for this date.
        </span>
      </Row>
    )
  }
  if (!wasConverted(entry)) return null

  return (
    <>
      <Row label={`Debit (${entry.base_currency})`}>
        <Value>
          {entry.base_debit_amount
            ? formatMoney(entry.base_debit_amount, entry.base_currency)
            : null}
        </Value>
      </Row>
      <Row label={`Credit (${entry.base_currency})`}>
        <Value>
          {entry.base_credit_amount
            ? formatMoney(entry.base_credit_amount, entry.base_currency)
            : null}
        </Value>
      </Row>
      <Row label="Exchange rate">
        <span className="tabular-nums">
          {toNumber(entry.fx_rate ?? 0).toLocaleString('en-GB', { maximumFractionDigits: 6 })}
        </span>{' '}
        <span className="text-muted-foreground">
          {entry.base_currency} per {entry.currency}
        </span>
      </Row>
      <Row label="Rate date">
        <Value>{entry.fx_rate_date}</Value>
      </Row>
    </>
  )
}

/** One posting's signed amount, as posted — the header figure a reader scans for. */
function PostingAmount({ entry }: { entry: ErpEntryRead }) {
  const amount = postingAmount(entry)
  return (
    <span className={cn('tabular-nums font-medium', amount < 0 && 'text-success')}>
      {formatMoney(amount, entry.currency)}
    </span>
  )
}

/**
 * One posting, collapsed to its account and amount until opened. A real
 * `<button>` with `aria-expanded`, not a `div` with a click handler — the
 * control has to be reachable and its state announced without a mouse.
 */
function PostingBlock({
  entry,
  open,
  onToggle,
}: {
  entry: ErpEntryRead
  open: boolean
  onToggle: () => void
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left outline-none hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="flex min-w-0 items-center gap-2">
          {open ? (
            <ChevronDown className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          ) : (
            <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          )}
          <span className="font-medium tabular-nums">{entry.erp_account_code}</span>
          <span className="truncate text-muted-foreground">{entry.erp_account_name}</span>
          {entry.status === 'failed' ? <Badge variant="destructive">failed</Badge> : null}
        </span>
        <PostingAmount entry={entry} />
      </button>

      {open ? (
        // The read-only treatment: a muted, non-interactive surface — never a
        // disabled input, which still reads as tappable.
        <dl className="divide-y divide-border bg-muted/30 px-4">
          <Row label="Description">
            <Value>{entry.description}</Value>
          </Row>
          <Row label="Entry type">{entry.entry_type}</Row>
          <Row label="Accounting date">
            <Value>{entry.accounting_date}</Value>
          </Row>
          <Row label="Supplier">
            <Value>{entry.vendor_name}</Value>
          </Row>
          <Row label="Source invoice">
            <Value>{entry.source_invoice_id}</Value>
          </Row>
          <Row label="Debit">
            <Value>
              {entry.debit_amount ? formatMoney(entry.debit_amount, entry.currency) : null}
            </Value>
          </Row>
          <Row label="Credit">
            <Value>
              {entry.credit_amount ? formatMoney(entry.credit_amount, entry.currency) : null}
            </Value>
          </Row>
          <Row label="Currency">
            <Value>{entry.currency}</Value>
          </Row>
          <ConversionRows entry={entry} />
          <Row label="Status">
            <Badge variant={entry.status === 'failed' ? 'destructive' : 'default'}>
              {entry.status}
            </Badge>
          </Row>
          {entry.error_message ? (
            <Row label="Error">
              <span className="text-destructive">{entry.error_message}</span>
            </Row>
          ) : null}
          <Row label="ERP entry id">
            <Value>{entry.erp_entry_id}</Value>
          </Row>
        </dl>
      ) : null}
    </div>
  )
}

export interface VoucherPostingsTabProps {
  entries: Array<ErpEntryRead>
}

/**
 * The Postings tab: every raw GL row the voucher is made of, each its own
 * collapsible block — an expense, its VAT, and the payable that balances it,
 * for the ordinary case. Presentational: no queries, no router.
 */
export function VoucherPostingsTab({ entries }: VoucherPostingsTabProps) {
  const [open, setOpen] = React.useState<Set<string>>(() => new Set())

  function toggle(id: string) {
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No postings on this voucher.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      {entries.map((entry) => (
        <PostingBlock
          key={entry.id}
          entry={entry}
          open={open.has(entry.id)}
          onToggle={() => toggle(entry.id)}
        />
      ))}
    </div>
  )
}
