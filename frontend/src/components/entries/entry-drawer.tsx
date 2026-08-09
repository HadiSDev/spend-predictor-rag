import {
  Badge,
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  Skeleton,
} from '#/components/ui'
import { formatMoney } from '#/lib/format'
import type { ErpEntryRead } from '#/lib/types'
import { ConversionRows, Row, Value } from './voucher-postings-tab'

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
