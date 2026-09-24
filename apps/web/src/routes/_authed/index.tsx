import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Card, Skeleton } from '#/components/ui'
import { DashboardBody } from '#/components/dashboard/body'
import { useApi } from '#/lib/auth'
import { entriesSummaryOptions, spendByCategoryOptions } from '#/lib/reports'

export const Route = createFileRoute('/_authed/')({
  component: DashboardPage,
  staticData: { title: 'Dashboard' },
})

function LoadingState() {
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-card" />
        ))}
      </div>
      <Skeleton className="h-72 rounded-card" />
    </div>
  )
}

function ErrorState() {
  return (
    <Card className="p-8 text-center">
      <h2 className="font-display text-base font-medium">Couldn’t load your dashboard</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        The reporting API request failed. Check that the web API is running and reachable, then
        reload the page.
      </p>
    </Card>
  )
}

function DashboardPage() {
  const api = useApi()
  const entries = useQuery(entriesSummaryOptions(api))
  const categories = useQuery(spendByCategoryOptions(api))

  if (entries.isPending || categories.isPending) return <LoadingState />
  if (entries.isError || categories.isError) return <ErrorState />

  return <DashboardBody entryRows={entries.data.rows} categoryRows={categories.data.rows} />
}
