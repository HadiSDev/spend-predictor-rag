import { type ColumnDef, DataTable } from '#/components/ui'
import { formatCount, formatMoney, toNumber } from '#/lib/format'
import type { CategorySpendRow } from '#/lib/types'

const columns: Array<ColumnDef<CategorySpendRow>> = [
  {
    accessorKey: 'level_2',
    header: 'Category',
    cell: ({ getValue }) => getValue<string | null>() ?? '—',
  },
  {
    accessorKey: 'currency',
    header: 'Currency',
    cell: ({ getValue }) => getValue<string | null>() ?? '—',
  },
  {
    accessorKey: 'amount_total',
    header: 'Amount',
    meta: { align: 'right' },
    cell: ({ row }) => (
      <span className="font-mono tabular-nums">
        {formatMoney(row.original.amount_total, row.original.currency)}
      </span>
    ),
    sortingFn: (a, b) => toNumber(a.original.amount_total) - toNumber(b.original.amount_total),
  },
  {
    accessorKey: 'count',
    header: 'Lines',
    meta: { align: 'right' },
    cell: ({ getValue }) => <span className="tabular-nums">{formatCount(getValue<number>())}</span>,
  },
]

/** Categorized spend by level-2 category, highest amount first. */
export function CategorySpendTable({ rows }: { rows: Array<CategorySpendRow> }) {
  const sorted = [...rows].sort(
    (a, b) => toNumber(b.amount_total) - toNumber(a.amount_total),
  )
  return (
    <DataTable
      columns={columns}
      data={sorted}
      pageSize={10}
      getRowId={(r, i) => `${r.level_2 ?? 'none'}-${r.currency ?? 'none'}-${i}`}
      emptyMessage="No categorized spend yet."
    />
  )
}
