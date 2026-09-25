import * as React from 'react'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  Input,
  Skeleton,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
} from '#/components/ui'
import type { ErpAccountRead, ErpAccountUpdate } from '#/lib/api/types'

/** Matches an account on code or name. */
function matches(account: ErpAccountRead, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) {
    return true
  }
  return (
    account.erp_account_code.toLowerCase().includes(q) ||
    account.erp_account_name.toLowerCase().includes(q)
  )
}

export interface AccountsPanelProps {
  companyName: string
  accounts: Array<ErpAccountRead>
  loading?: boolean
  canManage: boolean
  /** False when the company has no connected integration. */
  hasIntegration: boolean
  onToggle: (id: string, changes: ErpAccountUpdate) => Promise<unknown>
  onRefresh: () => Promise<{ seen: number; added: number }>
  onBack: () => void
}

/** A company's ERP chart of accounts and the settings we own on it. */
export function AccountsPanel({
  companyName,
  accounts,
  loading,
  canManage,
  hasIntegration,
  onToggle,
  onRefresh,
  onBack,
}: AccountsPanelProps) {
  const [query, setQuery] = React.useState('')
  const [busy, setBusy] = React.useState<Set<string>>(new Set())
  const [errors, setErrors] = React.useState<Record<string, string>>({})
  const [refreshing, setRefreshing] = React.useState(false)
  const [refreshResult, setRefreshResult] = React.useState<string | null>(null)

  const shown = accounts.filter((a) => matches(a, query))
  const enabledCount = accounts.filter((a) => a.sync_enabled).length

  async function toggle(account: ErpAccountRead, changes: ErpAccountUpdate) {
    setBusy((b) => new Set(b).add(account.id))
    setErrors(({ [account.id]: _drop, ...rest }) => rest)
    try {
      await onToggle(account.id, changes)
    } catch (err) {
      setErrors((e) => ({
        ...e,
        [account.id]: err instanceof Error ? err.message : 'Could not save',
      }))
    } finally {
      setBusy((b) => {
        const next = new Set(b)
        next.delete(account.id)
        return next
      })
    }
  }

  /** Bulk-updates the shown accounts only, a few requests at a time. */
  async function setAllShown(sync_enabled: boolean) {
    const targets = shown.filter((a) => a.sync_enabled !== sync_enabled)
    const queue = [...targets]
    const workers = Array.from(
      { length: Math.min(6, queue.length) },
      async () => {
        for (let next = queue.shift(); next; next = queue.shift()) {
          await toggle(next, { sync_enabled })
        }
      },
    )
    await Promise.all(workers)
  }

  async function refresh() {
    setRefreshing(true)
    setRefreshResult(null)
    try {
      const { seen, added } = await onRefresh()
      setRefreshResult(
        added > 0
          ? `${seen} accounts seen, ${added} added.`
          : `${seen} accounts seen, none new.`,
      )
    } catch (err) {
      setRefreshResult(err instanceof Error ? err.message : 'Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-12 rounded-md" />
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ArrowLeft className="size-4" />
          Companies
        </button>
        <h2 className="mt-2 font-display text-lg font-medium tracking-tight">
          {companyName} — ERP accounts
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          <strong className="font-medium text-foreground">Sync</strong> controls
          whether future syncs pull this account's entries; switching it off
          keeps everything already synced.{' '}
          <strong className="font-medium text-foreground">VAT</strong> records
          whether the account is assumed to include VAT, which is how a parsed
          invoice is read when reconciling it against what was posted. It
          recalculates nothing on its own.
        </p>
      </div>

      {!hasIntegration ? (
        <Card className="p-8 text-center">
          <h3 className="font-display text-base font-medium">
            No ERP connection
          </h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            This company has no connected ERP integration, so there is no chart
            of accounts to manage.
          </p>
        </Card>
      ) : accounts.length === 0 ? (
        <Card className="p-8 text-center">
          <h3 className="font-display text-base font-medium">
            No accounts fetched yet
          </h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            The chart of accounts has not been read from the ERP. Fetch it to
            choose which accounts to sync.
          </p>
          <div className="mt-4">
            <Button
              variant="outline"
              onClick={refresh}
              disabled={!canManage || refreshing}
            >
              <RefreshCw
                className={cn('size-4', refreshing && 'animate-spin')}
              />
              Refresh from ERP
            </Button>
          </div>
          {refreshResult ? (
            <p className="mt-3 text-sm text-muted-foreground">
              {refreshResult}
            </p>
          ) : null}
        </Card>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Input
              placeholder="Search code or name"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search accounts"
              className="w-64"
            />
            <span className="text-sm text-muted-foreground">
              {accounts.length} accounts · {enabledCount} synced
              {query ? ` · ${shown.length} shown` : ''}
            </span>
            <div className="ml-auto flex items-center gap-2">
              <Button
                variant="outline"
                disabled={!canManage || shown.length === 0}
                onClick={() => setAllShown(true)}
              >
                Enable {shown.length} shown
              </Button>
              <Button
                variant="outline"
                disabled={!canManage || shown.length === 0}
                onClick={() => setAllShown(false)}
              >
                Disable {shown.length} shown
              </Button>
              <Button
                variant="outline"
                onClick={refresh}
                disabled={!canManage || refreshing}
              >
                <RefreshCw
                  className={cn('size-4', refreshing && 'animate-spin')}
                />
                Refresh from ERP
              </Button>
            </div>
          </div>

          {refreshResult ? (
            <p className="text-sm text-muted-foreground">{refreshResult}</p>
          ) : null}
          {!canManage ? (
            <p className="text-sm text-muted-foreground">
              You have read-only access to this organization's companies, so
              these settings cannot be changed.
            </p>
          ) : null}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-24">Code</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="w-24">Sync</TableHead>
                <TableHead className="w-24">VAT</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((account) => (
                <TableRow key={account.id}>
                  <TableCell className="font-medium tabular-nums">
                    {account.erp_account_code}
                  </TableCell>
                  <TableCell>
                    {account.erp_account_name}
                    {!account.is_active ? (
                      <Badge variant="outline" className="ml-2">
                        inactive in ERP
                      </Badge>
                    ) : null}
                    {errors[account.id] ? (
                      <p className="mt-1 text-xs text-destructive">
                        {errors[account.id]}
                      </p>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {account.erp_account_type ?? '—'}
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={account.sync_enabled}
                      disabled={!canManage || busy.has(account.id)}
                      aria-label={`Sync ${account.erp_account_code}`}
                      onCheckedChange={(next) =>
                        toggle(account, { sync_enabled: next })
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={account.with_vat}
                      disabled={!canManage || busy.has(account.id)}
                      aria-label={`VAT on ${account.erp_account_code}`}
                      onCheckedChange={(next) =>
                        toggle(account, { with_vat: next })
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {shown.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground">
              No accounts match “{query}”.
            </p>
          ) : null}
        </>
      )}
    </div>
  )
}
