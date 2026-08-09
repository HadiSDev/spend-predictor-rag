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
import type { VoucherKey } from '#/lib/entries'
import { formatMoney, toNumber } from '#/lib/format'
import type { InvoiceLineRead, LineOrigin, VoucherGroupRead, VoucherTab } from '#/lib/types'
import { ConvertedAmount } from './converted-amount'

const dateFormatter = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' })

function formatDate(value: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed)
}

/** A quantity without its stored trailing zeros — `2.0000` reads as `2`. */
function formatQuantity(value: string | number): string {
  const parsed = toNumber(value)
  return Number.isNaN(parsed) ? String(value) : parsed.toLocaleString('en-GB')
}

/** A group is a real voucher when it has an id; otherwise it is a lone posting. */
function groupKey(group: VoucherGroupRead): string {
  return group.voucher_id ?? group.entries[0]?.id ?? group.company_id
}

function hasFailure(group: VoucherGroupRead): boolean {
  return group.entries.some((entry) => entry.status === 'failed')
}

/**
 * The group's net spend — the voucher's *expense* postings, netted. One signed
 * figure rather than a debit and a credit column: a voucher balances by
 * construction, so those two always carry the same number, and neither is what
 * a buyer wants to read.
 *
 * Deliberately **not** the sum of the rows this group expands to. Those are
 * every posting the voucher has, VAT and counterparty included, so they add up
 * to zero. That is why the column is headed "Total Spend" and not "Total": the
 * figure is a different quantity from its children, not a total of them.
 *
 * Negative means spend was reduced — a refund credits the account it originally
 * debited — so it is tinted rather than left to be misread as a charge.
 */
function GroupAmount({ group }: { group: VoucherGroupRead }) {
  // Converted into one currency, a voucher posted in several no longer reads as
  // "mixed" — this only fires when its postings genuinely cannot be added.
  if (group.currency === null && group.entries.length > 1 && group.unconverted_count === 0) {
    return <span className="text-xs text-muted-foreground">Mixed currencies</span>
  }
  // Nothing here could be converted, so there is no total to state — as opposed
  // to a total of zero.
  if (group.currency === null && group.unconverted_count > 0) {
    return <span className="text-xs text-muted-foreground">Not converted</span>
  }
  // A payment moves money without spending it: no amount, rather than a 0.00
  // that reads like a figure.
  if (group.amount === null) {
    return <span className="text-muted-foreground">—</span>
  }
  const negative = toNumber(group.amount) < 0
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn('tabular-nums', negative && 'text-success')}>
        {formatMoney(group.amount, group.currency)}
      </span>
      {/* The total leaves postings out, so it must not read as the whole. */}
      {group.unconverted_count > 0 ? <IncompleteMarker count={group.unconverted_count} /> : null}
    </span>
  )
}

/** Says a total excludes postings, rather than letting it pass as complete. */
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
        {count === 1 ? '1 posting is' : `${count} postings are`} not converted and not
        included in this total.
      </TooltipContent>
    </Tooltip>
  )
}

/**
 * A line's spend category as its full path — `Indirect › Legal › Professional
 * Services`.
 *
 * Empty when the line is not categorized yet, which is not a state the reader
 * can act on from this table.
 */
export function SpendCategory({ line }: { line: InvoiceLineRead }) {
  const path = [line.level_1, line.level_2, line.level_3].filter(
    (level): level is string => Boolean(level),
  )

  if (path.length === 0) return <span className="text-muted-foreground">—</span>
  return (
    <span className="text-muted-foreground">
      {path.map((level, i) => (
        <span key={level}>
          {i > 0 ? <span className="mx-1 opacity-50">›</span> : null}
          {/* The leaf is the answer; the levels above it are context. */}
          <span className={cn(i === path.length - 1 && 'text-foreground')}>{level}</span>
        </span>
      ))}
    </span>
  )
}

/**
 * Says a line stands in for a posting because no document was read.
 *
 * Information, not an error: most vouchers have no scan, so presenting this as a
 * problem would flag most of the ledger. Only `entry_fallback` is marked —
 * marking the ordinary extracted case too would make the marking meaningless.
 *
 * `tabIndex` and `aria-label` rather than colour or a bare icon: the whole
 * content of the mark is the explanation, so it has to reach a keyboard and a
 * screen-reader user identically.
 */
export function ProvenanceMark({ origin }: { origin: LineOrigin }) {
  if (origin !== 'entry_fallback') return null
  const explanation =
    'Stands in for a ledger posting — no document was read for this voucher, ' +
    'so this is the bookkeeper’s description rather than what was bought.'
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            tabIndex={0}
            aria-label={explanation}
            className="cursor-help rounded border border-border px-1 text-[10px] leading-4 text-muted-foreground"
          />
        }
      >
        from posting
      </TooltipTrigger>
      <TooltipContent>{explanation}</TooltipContent>
    </Tooltip>
  )
}

/**
 * The supplier's invoice number, preferring the one read off the document.
 *
 * The as-posted value is frequently not an invoice number at all: Billy's
 * `suppliersInvoiceNo` is user-entered and often null and `voucherNo` is blank
 * at least as often, so the connector falls back to the bill id — an internal
 * identifier sitting where the reader expects the supplier's number.
 *
 * When the two exist and disagree, the posted one stays reachable rather than
 * being silently discarded: a disagreement means the ERP's number is wrong, or
 * the scan belongs to a different invoice, and both are worth knowing.
 */
function InvoiceNumber({ group }: { group: VoucherGroupRead }) {
  const printed = group.document_invoice_number
  const posted = group.invoice_number
  const shown = printed ?? posted

  if (!shown) return <span className="text-muted-foreground">—</span>
  if (!printed || !posted || printed === posted) {
    return <span className="tabular-nums">{shown}</span>
  }
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            tabIndex={0}
            aria-label={`${printed}, read from the document. The ERP posted ${posted}.`}
            className="cursor-help tabular-nums underline decoration-dotted underline-offset-4"
          />
        }
      >
        {printed}
      </TooltipTrigger>
      <TooltipContent>Read from the document. The ERP posted {posted}.</TooltipContent>
    </Tooltip>
  )
}

/**
 * Column headers for the lines a group expands to.
 *
 * The table's own header describes *vouchers*, so without this the description
 * lands under Voucher and the line's amount under Total Spend — columns whose
 * names say something else. Rendered once per open group rather than once for
 * the table, since groups expand independently and a header far above the rows
 * it names is no header at all.
 *
 * "Amount", not "Total Spend": this is one line's own figure, and the group's
 * figure is the net of the voucher's expense postings — a different quantity.
 */
function LineHeaderRow() {
  return (
    <TableRow className="bg-muted/25 hover:bg-transparent">
      <TableHead className="h-8" />
      <TableHead className="h-8 pl-8">Description</TableHead>
      <TableHead className="h-8 text-right">Quantity</TableHead>
      {/* Its own column, not appended to the quantity: the quantity is a
          right-aligned tabular figure meant to be scanned down a column, and a
          unit inside that cell breaks the alignment on every row that has one. */}
      <TableHead className="h-8">Unit</TableHead>
      <TableHead className="h-8">Spend category</TableHead>
      <TableHead className="h-8 text-right">Amount</TableHead>
    </TableRow>
  )
}

/** One invoice line — what was bought, not how it was posted. */
function LineRow({ line, onSelect }: { line: InvoiceLineRead; onSelect: () => void }) {
  return (
    <TableRow className="bg-muted/25">
      <TableCell />
      <TableCell className="pl-8">
        <button
          type="button"
          onClick={onSelect}
          className="text-left outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          {line.description ?? <span className="text-muted-foreground">—</span>}
        </button>{' '}
        <ProvenanceMark origin={line.origin} />
      </TableCell>
      <TableCell className="text-right tabular-nums text-muted-foreground">
        {line.quantity === null ? '—' : formatQuantity(line.quantity)}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {/* No default substituted: "pcs" assumed over an hourly consulting line
            is a wrong figure presented with confidence. */}
        {line.unit ?? '—'}
      </TableCell>
      <TableCell>
        <SpendCategory line={line} />
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
  /** Opens the voucher-wide panel — by voucher id when the group has one,
   *  by the clicked posting's entry id otherwise (a voucherless group has no
   *  other shareable key). A `tab` is passed when the row that was activated
   *  says which face of the panel to open on. */
  onSelectEntry: (key: VoucherKey & { tab?: VoucherTab }) => void
}

/**
 * Synced postings, grouped as the ledger records them: one voucher, several
 * entries. Built on the `Table` primitives rather than `DataTable` — that one
 * paginates client-side over flat rows, and these rows are server-paginated
 * expandable groups.
 */
export function VoucherTable({ groups, onSelectEntry }: VoucherTableProps) {
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set())

  function toggle(key: string) {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-10" />
          <TableHead>Voucher</TableHead>
          {/* The supplier's own number, which is what a human reconciles
              against — not the ERP's voucher sequence beside it. */}
          <TableHead>Invoice no.</TableHead>
          <TableHead>Supplier</TableHead>
          <TableHead>Date</TableHead>
          {/* No Type column. Payments are excluded server-side, so what is left
              is overwhelmingly purchase_invoice — a column that reads the same
              on every row is noise. The type is still in the drawer, and is
              still a filter. Dropping it also squares the header with the five
              cells a posting row spans, which were a column short. */}
          {/* "Total Spend", not "Total": the rows a group expands to are the
              whole voucher and sum to zero, so this figure is a different
              quantity from its children rather than a total of them. */}
          <TableHead className="text-right">Total Spend</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {groups.map((group) => {
          const key = groupKey(group)
          const postings = group.entries
          const lines = group.lines
          // Expandable whenever the voucher has a line to reveal. A voucher with
          // none — a journal entry, a transfer, a voucher of only non-expense
          // postings — stays an ordinary row that still opens the panel, where
          // its postings are listed. That is the only place they live now.
          const expandable = lines.length > 0
          const isOpen = expanded.has(key)
          // Voucher id when the group has one, else the entry id of its lone
          // posting — a voucherless group has no other shareable key.
          const openGroup = () =>
            onSelectEntry({ voucher: group.voucher_id ?? undefined, entry: postings[0]?.id })
          return (
            <React.Fragment key={key}>
              <TableRow className={cn(expandable && 'cursor-pointer')}>
                <TableCell className="pr-0">
                  {expandable ? (
                    <IconButton
                      variant="ghost"
                      aria-label={`${isOpen ? 'Collapse' : 'Expand'} voucher ${group.voucher_id}`}
                      aria-expanded={isOpen}
                      onClick={() => toggle(key)}
                    >
                      {isOpen ? <ChevronDown /> : <ChevronRight />}
                    </IconButton>
                  ) : null}
                </TableCell>
                <TableCell className="font-medium">
                  {/* The name is always its own control, separate from the
                      expand/collapse chevron: expanding reveals the postings
                      inline, opening the panel is a different action, and a
                      group of one posting has nothing to expand at all — the
                      row itself has to be the way into the panel for it. */}
                  <button
                    type="button"
                    onClick={openGroup}
                    aria-label={`View voucher ${group.voucher_id ?? 'with no id'}`}
                    className={cn(
                      'text-left outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring',
                      group.voucher_id === null && 'text-muted-foreground italic',
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
                <TableCell>{group.vendor_name ?? <span className="text-muted-foreground">—</span>}</TableCell>
                <TableCell className="whitespace-nowrap">{formatDate(group.accounting_date)}</TableCell>
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
                      // Opens the panel on its Lines tab: the row the reader
                      // activated is a line, so that is what should be in view.
                      onSelect={() =>
                        onSelectEntry({
                          voucher: group.voucher_id ?? undefined,
                          entry: postings[0]?.id,
                          tab: 'lines',
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
