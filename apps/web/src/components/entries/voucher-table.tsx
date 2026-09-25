import * as React from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import {
  Badge,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  cn,
} from '#/components/ui'
import type { VoucherSelection } from '#/lib/api/entries'
import { formatMoney, toNumber } from '#/lib/format/format'
import type { InvoiceLineRead, VoucherGroupRead } from '#/lib/api/types'
import { ConvertedAmount } from './converted-amount'
import { LineStatusBadge } from './lines/line-status'
import { ProvenanceMark } from './lines/provenance-mark'
import { SpendCategory } from './lines/spend-category'

const dateFormatter = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' })

function formatDate(value: string | null): string {
  if (!value) {
    return '—'
  }
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed)
}

/** A quantity without trailing zeros. */
function formatQuantity(value: string | number): string {
  const parsed = toNumber(value)
  return Number.isNaN(parsed) ? String(value) : parsed.toLocaleString('en-GB')
}

function groupKey(group: VoucherGroupRead): string {
  return group.voucher_id ?? group.entries[0]?.id ?? group.company_id
}

function hasFailure(group: VoucherGroupRead): boolean {
  return group.entries.some((entry) => entry.status === 'failed')
}

/** The group's net spend: its expense postings, netted. */
function GroupAmount({ group }: { group: VoucherGroupRead }) {
  if (
    group.currency === null &&
    group.entries.length > 1 &&
    group.unconverted_count === 0
  ) {
    return (
      <span className="text-xs text-muted-foreground">Mixed currencies</span>
    )
  }
  if (group.currency === null && group.unconverted_count > 0) {
    return <span className="text-xs text-muted-foreground">Not converted</span>
  }
  if (group.amount === null) {
    return <span className="text-muted-foreground">—</span>
  }
  const negative = toNumber(group.amount) < 0
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={cn('font-mono tabular-nums', negative && 'text-success')}
      >
        {formatMoney(group.amount, group.currency)}
      </span>
      {group.unconverted_count > 0 ? (
        <IncompleteMarker count={group.unconverted_count} />
      ) : null}
    </span>
  )
}

/** Notes that a total excludes some postings. */
function IncompleteMarker({ count }: { count: number }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            tabIndex={0}
            aria-label={`${count} ${count === 1 ? 'posting is' : 'postings are'} not converted and not included in this total`}
            className="cursor-help text-xs text-muted-foreground"
          />
        }
      >
        +{count}*
      </TooltipTrigger>
      <TooltipContent>
        {count === 1 ? '1 posting is' : `${count} postings are`} not converted
        and not included in this total.
      </TooltipContent>
    </Tooltip>
  )
}

/** The supplier's invoice number, preferring the one read off the document. */
function InvoiceNumber({ group }: { group: VoucherGroupRead }) {
  const printed = group.document_invoice_number
  const posted = group.invoice_number
  const shown = printed ?? posted

  if (!shown) {
    return <span className="text-muted-foreground">—</span>
  }
  if (!printed || !posted || printed === posted) {
    return <span className="font-mono tabular-nums">{shown}</span>
  }
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            tabIndex={0}
            aria-label={`${printed}, read from the document. The ERP posted ${posted}.`}
            className="cursor-help font-mono tabular-nums underline decoration-dotted underline-offset-4"
          />
        }
      >
        {printed}
      </TooltipTrigger>
      <TooltipContent>
        Read from the document. The ERP posted {posted}.
      </TooltipContent>
    </Tooltip>
  )
}

/** Column headers for the lines a group expands to. */
function LineHeaderRow() {
  return (
    <TableRow className="bg-muted/25 hover:bg-transparent">
      <TableHead className="h-8" />
      <TableHead className="h-8 pl-8">Description</TableHead>
      <TableHead className="h-8 text-right">Quantity</TableHead>
      <TableHead className="h-8">Unit</TableHead>
      <TableHead className="h-8 text-right">Unit price</TableHead>
      <TableHead className="h-8">Spend category</TableHead>
      <TableHead className="h-8">Status</TableHead>
      <TableHead className="h-8 text-right">Amount</TableHead>
    </TableRow>
  )
}

/** What to call a line: its name, else its description, else an explicit mark. */
function LineLabel({ line }: { line: InvoiceLineRead }) {
  const label = line.item_name ?? line.description
  if (label === null || label === '') {
    return <span className="text-muted-foreground">Unnamed line</span>
  }
  return <>{label}</>
}

/** One invoice line row. */
function LineRow({
  line,
  onSelect,
}: {
  line: InvoiceLineRead
  onSelect: () => void
}) {
  return (
    <TableRow className="cursor-pointer bg-muted/25" onClick={onSelect}>
      <TableCell />
      <TableCell className="pl-8">
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation()
            onSelect()
          }}
          className="text-left outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          <LineLabel line={line} />
        </button>{' '}
        <ProvenanceMark origin={line.origin} />
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
        {line.quantity === null ? '—' : formatQuantity(line.quantity)}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {line.unit ?? '—'}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
        {line.unit_price === null
          ? '—'
          : formatMoney(line.unit_price, line.currency)}
      </TableCell>
      <TableCell>
        <SpendCategory line={line} />
      </TableCell>
      <TableCell>
        <LineStatusBadge line={line} />
      </TableCell>
      <TableCell className="text-right">
        <ConvertedAmount
          row={line}
          base={line.base_amount}
          posted={line.amount}
          postedCurrency={line.currency}
          signed
        />
      </TableCell>
    </TableRow>
  )
}

export interface VoucherTableProps {
  groups: Array<VoucherGroupRead>
  /** Opens the voucher panel by voucher id, or by entry id for a voucherless group. */
  onSelectEntry: (key: VoucherSelection) => void
}

/** Synced postings grouped by voucher. */
export function VoucherTable({ groups, onSelectEntry }: VoucherTableProps) {
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set())

  function toggle(key: string) {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-10" />
          <TableHead>Voucher</TableHead>
          <TableHead>Invoice no.</TableHead>
          <TableHead colSpan={3}>Supplier</TableHead>
          <TableHead>Date</TableHead>
          <TableHead className="text-right">Total Spend</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {groups.map((group) => {
          const key = groupKey(group)
          const postings = group.entries
          const lines = group.lines
          const expandable = lines.length > 0
          const isOpen = expanded.has(key)
          const openGroup = () =>
            onSelectEntry({
              voucher: group.voucher_id ?? undefined,
              entry: postings[0]?.id,
            })
          return (
            <React.Fragment key={key}>
              <TableRow className="cursor-pointer" onClick={openGroup}>
                <TableCell className="pr-0">
                  {expandable ? (
                    <IconButton
                      variant="ghost"
                      aria-label={`${isOpen ? 'Collapse' : 'Expand'} voucher ${group.voucher_id}`}
                      aria-expanded={isOpen}
                      onClick={(event) => {
                        event.stopPropagation()
                        toggle(key)
                      }}
                    >
                      {isOpen ? <ChevronDown /> : <ChevronRight />}
                    </IconButton>
                  ) : null}
                </TableCell>
                <TableCell className="font-medium">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation()
                      openGroup()
                    }}
                    aria-label={`View voucher ${group.voucher_id ?? 'with no id'}`}
                    className={cn(
                      'text-left outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring',
                      group.voucher_id === null &&
                        'text-muted-foreground italic',
                    )}
                  >
                    {group.voucher_id ?? 'No voucher'}
                  </button>
                  {hasFailure(group) ? (
                    <Badge variant="destructive" className="ml-2">
                      failed
                    </Badge>
                  ) : null}
                </TableCell>
                <TableCell>
                  <InvoiceNumber group={group} />
                </TableCell>
                <TableCell colSpan={3}>
                  {group.vendor_name ?? (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  {formatDate(group.accounting_date)}
                </TableCell>
                <TableCell className="text-right">
                  <GroupAmount group={group} />
                </TableCell>
              </TableRow>
              {isOpen ? (
                <>
                  <LineHeaderRow />
                  {lines.map((line) => (
                    <LineRow
                      key={line.id}
                      line={line}
                      onSelect={() =>
                        onSelectEntry({
                          voucher: group.voucher_id ?? undefined,
                          entry: postings[0]?.id,
                          tab: 'lines',
                          line: line.id,
                        })
                      }
                    />
                  ))}
                </>
              ) : null}
            </React.Fragment>
          )
        })}
      </TableBody>
    </Table>
  )
}
