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
import { basePostingAmount, postingAmount } from '#/lib/entry-amount'
import type { VoucherKey } from '#/lib/entries'
import { formatMoney, toNumber } from '#/lib/format'
import type { ErpEntryRead, VoucherGroupRead } from '#/lib/types'
import { ConvertedAmount } from './converted-amount'

const dateFormatter = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' })

function formatDate(value: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed)
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
 * The spend category of the invoice line this posting came from, as its full
 * path — `Indirect › Legal › Professional Services`.
 *
 * The category is never the posting's own: it belongs to the line, and one line
 * may be posted as several entries, which then all read the same category here.
 *
 * Empty for two different reasons that deliberately look identical — the
 * posting has no line behind it (VAT, the payable), or its line has not been
 * categorized yet. Neither is a state the reader can act on from this table.
 */
function SpendCategory({ entry }: { entry: ErpEntryRead }) {
  const path = [
    entry.spend_category_level_1,
    entry.spend_category_level_2,
    entry.spend_category_level_3,
  ].filter((level): level is string => Boolean(level))

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
 * Column headers for the postings a group expands to.
 *
 * The table's own header describes *vouchers*, so without this the account
 * lands under Voucher, the line text under Date, and the posting's amount under
 * Total Spend — three columns whose names say something else. Rendered once per
 * open group rather than once for the table, since groups expand independently
 * and a header far above the rows it names is no header at all.
 *
 * "Amount", not "Total Spend": this is one posting's own debit − credit, and
 * the VAT and payable rows are not spend at all.
 */
function PostingHeaderRow() {
  return (
    <TableRow className="bg-muted/25 hover:bg-transparent">
      <TableHead className="h-8" />
      {/* One cell per column now that Spend category is here — the account
          cell used to span two, which leaves no room for a fifth. */}
      <TableHead className="h-8 pl-8">Account</TableHead>
      <TableHead className="h-8">Description</TableHead>
      <TableHead className="h-8">Spend category</TableHead>
      <TableHead className="h-8 text-right">Amount</TableHead>
    </TableRow>
  )
}

/** One posting. Debit and credit are collapsed into a single signed
 *  figure — the only thing being asked of this table. */
function EntryRow({
  entry,
  onSelect,
}: {
  entry: ErpEntryRead
  onSelect: () => void
}) {
  const amount = postingAmount(entry)
  const base = basePostingAmount(entry)
  return (
    <TableRow className="bg-muted/25">
      <TableCell />
      <TableCell className="pl-8">
        <button
          type="button"
          onClick={onSelect}
          className="text-left outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="font-medium tabular-nums">{entry.erp_account_code}</span>{' '}
          <span className="text-muted-foreground">{entry.erp_account_name}</span>
        </button>
      </TableCell>
      <TableCell className="text-muted-foreground">
        {entry.description ?? '—'}
        {entry.status === 'failed' ? (
          <Badge variant="destructive" className="ml-2">
            failed
          </Badge>
        ) : null}
      </TableCell>
      <TableCell>
        <SpendCategory entry={entry} />
      </TableCell>
      <TableCell className="text-right">
        <ConvertedAmount
          row={entry}
          base={base}
          posted={amount}
          postedCurrency={entry.currency}
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
   *  other shareable key). */
  onSelectEntry: (key: VoucherKey) => void
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
          // Expandable whenever there is more than one posting to reveal.
          // Nothing is filtered out any more, so an ordinary purchase — expense,
          // VAT, payable — does expand. That is the point: the ledger detail was
          // always fetched and was previously unreachable.
          const expandable = postings.length > 1
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
                <TableCell>{group.vendor_name ?? <span className="text-muted-foreground">—</span>}</TableCell>
                <TableCell className="whitespace-nowrap">{formatDate(group.accounting_date)}</TableCell>
                <TableCell className="text-right">
                  <GroupAmount group={group} />
                </TableCell>
              </TableRow>
              {isOpen ? (
                <>
                  <PostingHeaderRow />
                  {postings.map((entry) => (
                    <EntryRow
                      key={entry.id}
                      entry={entry}
                      onSelect={() =>
                        onSelectEntry({ voucher: group.voucher_id ?? undefined, entry: entry.id })
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
