import { Activity, Layers, Wallet } from 'lucide-react'
import { StatCard } from '#/components/ui'
import { formatCount, formatMoney, toNumber } from '#/lib/format/format'
import type { EntrySummaryRow } from '#/lib/api/types'

/** Sum net per currency (never across currencies) from entries-summary rows. */
function netByCurrency(
  rows: Array<EntrySummaryRow>,
): Array<{ currency: string | null; net: number }> {
  const totals = new Map<string | null, number>()
  for (const row of rows) {
    totals.set(
      row.currency,
      (totals.get(row.currency) ?? 0) + toNumber(row.net),
    )
  }
  return [...totals.entries()].map(([currency, net]) => ({ currency, net }))
}

/** Stat cards: net ledger balance per currency + total transaction count. */
export function DashboardStats({ rows }: { rows: Array<EntrySummaryRow> }) {
  const nets = netByCurrency(rows)
  const totalCount = rows.reduce((sum, r) => sum + r.count, 0)
  const entryTypes = new Set(rows.map((r) => r.entry_type)).size

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {nets.map(({ currency, net }) => (
        <StatCard
          key={currency ?? 'none'}
          icon={<Wallet />}
          label={currency ? `Net ledger · ${currency}` : 'Net ledger'}
          value={formatMoney(net, currency)}
        />
      ))}
      <StatCard
        icon={<Activity />}
        label="Transactions"
        value={formatCount(totalCount)}
      />
      <StatCard
        icon={<Layers />}
        label="Entry types"
        value={formatCount(entryTypes)}
      />
    </div>
  )
}
