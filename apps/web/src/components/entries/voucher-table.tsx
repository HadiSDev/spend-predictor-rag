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
import type { VoucherSelection } from '#/lib/entries'
import { formatMoney, toNumber } from '#/lib/format'
import type { InvoiceLineRead, LineOrigin, VoucherGroupRead } from '#/lib/types'
import { ConvertedAmount } from './converted-amount'
import { LineStatusBadge } from './line-status'

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
 * problem would flag most of the ledger. Only the two origins a reader would
 * not otherwise expect are marked — `entry_fallback`, whose description is a
 * memo rather than a purchase, and `human`, which no automated source produced.
 * Marking the ordinary ERP and extracted cases too would make the mark
 * meaningless.
 *
 * `tabIndex` and `aria-label` rather than colour or a bare icon: the whole
 * content of the mark is the explanation, so it has to reach a keyboard and a
 * screen-reader user identically.
 */
const PROVENANCE_MARKS: Partial<Record<LineOrigin, { label: string; explanation: string }>> = {
  entry_fallback: {
    label: 'from posting',
    explanation:
      'Stands in for a ledger posting — no document was read for this voucher, ' +
      'so this is the bookkeeper’s description rather than what was bought.',
  },
  human: {
    label: 'added by hand',
    explanation:
      'Written by a reviewer rather than read from the ERP or the document. ' +
      'A sync will not change or remove it.',
  },
}

export function ProvenanceMark({ origin }: { origin: LineOrigin }) {
  const mark = PROVENANCE_MARKS[origin]
  if (mark === undefined) return null
  const { label, explanation } = mark
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
        {label}
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
      <TableHead className="h-8 text-right">Unit price</TableHead>
      <TableHead className="h-8">Spend category</TableHead>
      {/* Its own column, because an empty Spend category means "not tried
          yet", "tried and failed", and "no tree to try against" identically —
          and only the middle one is a problem worth acting on. */}
      <TableHead className="h-8">Status</TableHead>
      <TableHead className="h-8 text-right">Amount</TableHead>
    </TableRow>
  )
}

/**
 * What to call a line: its name, else its prose, else an explicit mark.
 *
 * The name is what the line *is*, and every line is expected to carry one. The
 * description is prose a supplier printed sometimes, and stands in only when
 * there is no name — a line predating the split, or one the model could not
 * name. Neither becomes an empty cell: a blank tells a reader nothing about
 * whether the document was silent or the extraction failed.
 */
function LineLabel({ line }: { line: InvoiceLineRead }) {
  const label = line.item_name ?? line.description
  if (label === null || label === '') {
    return <span className="text-muted-foreground">Unnamed line</span>
  }
  return <>{label}</>
}

/**
 * One invoice line — what was bought, not how it was posted.
 *
 * The whole row opens the panel, not just the label. A reader pressing a
 * row of a table expects the thing the row describes to open, and the
 * description is a short target in a row eight columns wide — press anywhere
 * else and nothing happened at all. The button inside stays, because a row is
 * not reachable from a keyboard and `onClick` on a `<tr>` is a mouse
 * affordance, never the only way in.
 */
function LineRow({ line, onSelect }: { line: InvoiceLineRead; onSelect: () => void }) {
  return (
    <TableRow className="cursor-pointer bg-muted/25" onClick={onSelect}>
      <TableCell />
      <TableCell className="pl-8">
        <button
          type="button"
          // The row handles this too, so the click is stopped here rather than
          // opening the same panel twice.
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
      <TableCell className="text-right tabular-nums text-muted-foreground">
        {line.quantity === null ? '—' : formatQuantity(line.quantity)}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {/* No default substituted: "pcs" assumed over an hourly consulting line
            is a wrong figure presented with confidence. */}
        {line.unit ?? '—'}
      </TableCell>
      <TableCell className="text-right tabular-nums text-muted-foreground">
        {/* As stated, in the currency it was stated in — not converted. There
            is no stored base unit price (only `base_amount` is converted), and
            deriving one here would make this the single place in the app that
            converts money in the browser. The Amount beside it still explains
            its own conversion. */}
        {line.unit_price === null ? '—' : formatMoney(line.unit_price, line.currency)}
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
  /** Opens the voucher-wide panel — by voucher id when the group has one,
   *  by the clicked posting's entry id otherwise (a voucherless group has no
   *  other shareable key). A `tab` is passed when the row that was activated
   *  says which face of the panel to open on. */
  onSelectEntry: (key: VoucherSelection) => void
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
          {/* Spans three because a line row carries two more columns than a
              voucher row does — Spend category and Status — and Amount has to
              stay under Total Spend: a figure that landed a column right of the
              total it belongs to would be read against the wrong header.
              Supplier takes the slack because its names are the longest text in
              the row. */}
          <TableHead colSpan={3}>Supplier</TableHead>
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
              {/* Pressable whether or not it expands: opening the panel is
                  what every row does, and the cursor has always promised it.
                  Before this the promise was empty — only the voucher number
                  itself was a control, so pressing the row did nothing. */}
              <TableRow className="cursor-pointer" onClick={openGroup}>
                <TableCell className="pr-0">
                  {expandable ? (
                    <IconButton
                      variant="ghost"
                      aria-label={`${isOpen ? 'Collapse' : 'Expand'} voucher ${group.voucher_id}`}
                      aria-expanded={isOpen}
                      // Expanding reveals the lines in place; opening the panel
                      // puts a sheet over them. Without this the chevron would
                      // do both, and the panel would cover what it just showed.
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
                  {/* The name stays its own control even though the row is
                      now pressable: a `<tr>` takes no focus and answers no
                      Enter key, so without a real button here the panel would
                      be unreachable without a mouse. */}
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation()
                      openGroup()
                    }}
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
                <TableCell colSpan={3}>
                  {group.vendor_name ?? <span className="text-muted-foreground">—</span>}
                </TableCell>
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
                          // Which line, so the panel opens on the row that was
                          // activated rather than on the invoice's first.
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
