import { BarChart3 } from 'lucide-react'
import { Card } from '#/components/ui'
import { CategorySpendTable } from './category-table'
import { DashboardStats } from './stats'
import type { CategorySpendRow, EntrySummaryRow } from '#/lib/api/types'

function EmptyState() {
  return (
    <Card className="p-10 text-center">
      <div className="mx-auto grid size-12 place-items-center rounded-xl bg-muted text-muted-foreground">
        <BarChart3 className="size-6" />
      </div>
      <h2 className="mt-4 font-display text-base font-medium">No data yet</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        Once transactions are synced and categorized, your spend figures will
        appear here.
      </p>
    </Card>
  )
}

/** Dashboard content: stat cards and a spend-by-category table, or an empty state. */
export function DashboardBody({
  entryRows,
  categoryRows,
}: {
  entryRows: Array<EntrySummaryRow>
  categoryRows: Array<CategorySpendRow>
}) {
  if (entryRows.length === 0 && categoryRows.length === 0) {
    return <EmptyState />
  }

  return (
    <div className="flex flex-col gap-6">
      {entryRows.length > 0 ? <DashboardStats rows={entryRows} /> : null}
      <Card className="p-5">
        <h2 className="mb-4 font-display text-base font-medium tracking-tight">
          Spend by category
        </h2>
        <CategorySpendTable rows={categoryRows} />
      </Card>
    </div>
  )
}
