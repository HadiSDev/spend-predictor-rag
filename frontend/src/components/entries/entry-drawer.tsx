import * as React from 'react'
import {
  Badge,
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  Skeleton,
} from '#/components/ui'
import { formatMoney, toNumber } from '#/lib/format'
import type { ErpEntryRead } from '#/lib/types'
import { wasConverted } from './converted-amount'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-3 py-2 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

function Value({ children }: { children: React.ReactNode }) {
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
function ConversionRows({ entry }: { entry: ErpEntryRead }) {
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

export interface EntryDrawerProps {
  entry: ErpEntryRead | undefined
  loading: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * One posting's full detail. A drawer rather than a dialog so the table stays
 * visible behind it — scanning many entries in a row is the normal case.
 */
export function EntryDrawer({ entry, loading, open, onOpenChange }: EntryDrawerProps) {
  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent side="right" aria-label="Entry detail">
        <DrawerHeader>
          <DrawerTitle>Entry detail</DrawerTitle>
          <DrawerDescription>
            The raw GL posting exactly as the ERP recorded it.
          </DrawerDescription>
        </DrawerHeader>

        {loading || !entry ? (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-6 rounded-md" />
            ))}
          </div>
        ) : (
          <dl className="divide-y divide-border">
            <Row label="Account">
              <span className="font-medium tabular-nums">{entry.erp_account_code}</span>{' '}
              <span className="text-muted-foreground">{entry.erp_account_name}</span>
            </Row>
            <Row label="Description">
              <Value>{entry.description}</Value>
            </Row>
            <Row label="Voucher">
              <Value>{entry.voucher_id}</Value>
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
        )}
      </DrawerContent>
    </Drawer>
  )
}
