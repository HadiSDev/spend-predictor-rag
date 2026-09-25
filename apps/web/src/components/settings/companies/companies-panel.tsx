import * as React from 'react'
import {
  Ban,
  ListChecks,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  Sparkles,
  RotateCcw,
  Trash2,
} from 'lucide-react'
import {
  Badge,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  IconButton,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  useToast,
} from '#/components/ui'
import type {
  CompanyRead,
  CompanyUpdateResult,
  ErpIntegrationRead,
  ErpTypeRead,
  FxRecomputeResult,
  RecategorizeResult,
  SpendTreeRead,
} from '#/lib/api/types'
import { serverErrorMessage } from '#/lib/form-errors'
import {
  ReadOnlyNotice,
  SettingsCard,
  SubmitHandled,
} from '#/components/settings/form'
import { CompanyDialog } from './company-dialog'
import {
  changedFields,
  deleteBlockedFrom,
  integrationsFor,
  replaceBlockedFrom,
  toValues,
} from './company-values'
import type {
  CompanyCreateValues,
  CompanyFormValues,
  CompanyValues,
  IntegrationChanges,
} from './company-values'
import { DeactivateCompanyDialog } from './deactivate-company-dialog'
import { DeleteCompanyDialog } from './delete-company-dialog'
import type { DeleteCompanyState } from './delete-company-dialog'
import { ErpSwitchDialog } from './erp-switch-dialog'
import type {
  ErpSwitchBlockedState,
  ErpSwitchValues,
} from './erp-switch-dialog'
import { RecategorizeDialog } from './recategorize-dialog'
import type { RecategorizeState } from './recategorize-dialog'
import { RecomputeDialog } from './recompute-dialog'
import type { RecomputeState } from './recompute-dialog'
import { StaleLinesDialog } from './stale-lines-dialog'
import type { StaleLinesState } from './stale-lines-dialog'

export interface CompaniesPanelProps {
  companies: Array<CompanyRead>
  loading?: boolean
  includeInactive: boolean
  onIncludeInactiveChange: (next: boolean) => void
  canManage: boolean
  /** Whether the reader holds the platform flag to delete companies outright. */
  canDelete?: boolean
  /** The connectable ERP systems, from `GET /erp-types`. */
  erpTypes?: Array<ErpTypeRead>
  erpTypesLoading?: boolean
  /** Integrations across every company in scope; each dialog picks out its own. */
  integrations?: Array<ErpIntegrationRead>
  /** The organization's active spend trees, for the company's tree picker. */
  spendTrees?: Array<SpendTreeRead>
  onCreate: (values: CompanyCreateValues) => Promise<unknown>
  onUpdate: (
    id: string,
    changes: Partial<CompanyValues>,
  ) => Promise<CompanyUpdateResult>
  /** Open the entries view filtered to the lines a tree change left stale. */
  onReviewStaleLines?: (companyId: string) => void
  /** Only the changed parts are sent; omitting `credentials` keeps the stored secret. */
  onUpdateIntegration?: (
    id: string,
    changes: IntegrationChanges,
  ) => Promise<unknown>
  /** Move a company to a different ERP by retiring its integration and starting a new one. */
  onReplaceIntegration?: (
    id: string,
    values: {
      erp_type: string
      label: string
      credentials: Record<string, string>
      confirm?: boolean
    },
  ) => Promise<unknown>
  /** Connect an ERP to a company that has none. */
  onConnectIntegration?: (
    companyId: string,
    values: {
      erp_type: string
      label: string
      credentials: Record<string, string>
    },
  ) => Promise<unknown>
  onSetActive: (id: string, active: boolean) => Promise<unknown>
  /** Destroy a company; rejects with the `409` body until confirmed. */
  onDelete: (id: string, confirm: boolean) => Promise<unknown>
  /** Rewrite a company's stored figures into its current reporting currency. */
  onRecomputeFx?: (companyId: string) => Promise<FxRecomputeResult>
  /** Put a company's `ai_failed` lines back in the categorizer's queue. */
  onRecategorize?: (companyId: string) => Promise<RecategorizeResult>
  /** Navigate to a company's ERP account settings. */
  onManageAccounts?: (companyId: string) => void
}

/** Settings panel listing the organization's companies and their actions. */
export function CompaniesPanel({
  companies,
  loading = false,
  includeInactive,
  onIncludeInactiveChange,
  canManage,
  canDelete = false,
  erpTypes = [],
  erpTypesLoading = false,
  integrations = [],
  spendTrees = [],
  onCreate,
  onReviewStaleLines,
  onUpdate,
  onUpdateIntegration,
  onReplaceIntegration,
  onConnectIntegration,
  onSetActive,
  onDelete,
  onRecomputeFx,
  onRecategorize,
  onManageAccounts,
}: CompaniesPanelProps) {
  const [dialogOpen, setDialogOpen] = React.useState(false)
  const [editing, setEditing] = React.useState<CompanyRead | null>(null)
  const [confirming, setConfirming] = React.useState<string | null>(null)
  const [deleting, setDeleting] = React.useState<DeleteCompanyState | null>(
    null,
  )
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [recomputing, setRecomputing] = React.useState<RecomputeState | null>(
    null,
  )
  const [recategorizing, setRecategorizing] =
    React.useState<RecategorizeState | null>(null)
  const [reassigned, setReassigned] = React.useState<StaleLinesState | null>(
    null,
  )
  const [blocked, setBlocked] = React.useState<ErpSwitchBlockedState | null>(
    null,
  )
  const [switchError, setSwitchError] = React.useState<string | null>(null)
  const [switchBusy, setSwitchBusy] = React.useState(false)
  const toast = useToast()

  const confirmingCompany = companies.find(
    (company) => company.id === confirming,
  )

  /** Attempt the ERP switch from `saveEdits`, opening the confirm dialog on a `409`. */
  async function saveIntegrationSwitch(
    integrationId: string,
    values: ErpSwitchValues,
  ) {
    try {
      await onReplaceIntegration?.(integrationId, values)
    } catch (err) {
      const counts = replaceBlockedFrom(err)
      if (!counts) {
        throw err
      }
      setBlocked({ integrationId, values, counts })
      throw new SubmitHandled()
    }
  }

  /** Re-post the ERP switch with the block acknowledged. */
  async function confirmSwitch() {
    if (!blocked || switchBusy) {
      return
    }
    setSwitchBusy(true)
    try {
      await onReplaceIntegration?.(blocked.integrationId, {
        ...blocked.values,
        confirm: true,
      })
      setBlocked(null)
      setSwitchError(null)
      toast.add({ title: 'ERP switched' })
      setDialogOpen(false)
    } catch (err) {
      setSwitchError(serverErrorMessage(err))
    } finally {
      setSwitchBusy(false)
    }
  }

  /** Save the company edit and its integration changes, each only if changed. */
  async function saveEdits(company: CompanyRead, values: CompanyFormValues) {
    const changes = changedFields(toValues(company), values)
    let result: CompanyUpdateResult | undefined
    if (Object.keys(changes).length > 0) {
      result = await onUpdate(company.id, changes)
    }
    const staleLines = result?.stale_lines ?? 0
    if (changes.spend_tree_id !== undefined && staleLines > 0) {
      setReassigned({ company, staleLines })
    }
    if (changes.base_currency && onRecomputeFx) {
      setRecomputing({
        company,
        currency: changes.base_currency,
        result: null,
        busy: false,
      })
    }

    const [integration] = integrationsFor(integrations, company.id)
    const credentials = Object.fromEntries(
      Object.entries(values.credentials).filter(
        ([, value]) => value.trim() !== '',
      ),
    )

    if (
      integration &&
      values.erp_type &&
      values.erp_type !== integration.erp_type
    ) {
      await saveIntegrationSwitch(integration.id, {
        erp_type: values.erp_type,
        label: values.label,
        credentials,
      })
    } else if (integration) {
      const integrationChanges: IntegrationChanges = {}
      if ((integration.label ?? '') !== values.label) {
        integrationChanges.label = values.label
      }
      if (values.replaceCredentials) {
        integrationChanges.credentials = credentials
      }
      if (Object.keys(integrationChanges).length > 0) {
        await onUpdateIntegration?.(integration.id, integrationChanges)
      }
    } else if (values.erp_type) {
      await onConnectIntegration?.(company.id, {
        erp_type: values.erp_type,
        label: values.label,
        credentials,
      })
    }
  }

  async function runRecategorize() {
    if (!recategorizing || !onRecategorize) {
      return
    }
    setRecategorizing({ ...recategorizing, busy: true })
    setError(null)
    try {
      const result = await onRecategorize(recategorizing.company.id)
      setRecategorizing((current) =>
        current ? { ...current, busy: false, result } : null,
      )
    } catch (failure) {
      setError(serverErrorMessage(failure))
      setRecategorizing((current) =>
        current ? { ...current, busy: false } : null,
      )
    }
  }

  async function runRecompute() {
    if (!recomputing || !onRecomputeFx) {
      return
    }
    setRecomputing({ ...recomputing, busy: true })
    setError(null)
    try {
      const result = await onRecomputeFx(recomputing.company.id)
      setRecomputing((current) =>
        current ? { ...current, busy: false, result } : null,
      )
    } catch (failure) {
      setError(serverErrorMessage(failure))
      setRecomputing((current) =>
        current ? { ...current, busy: false } : null,
      )
    }
  }

  async function toggleActive(company: CompanyRead) {
    setBusy(true)
    setError(null)
    try {
      await onSetActive(company.id, !company.is_active)
      setConfirming(null)
    } catch (failure) {
      setError(serverErrorMessage(failure))
    } finally {
      setBusy(false)
    }
  }

  /** Destroy the company, or fetch what it holds and ask again. */
  async function runDelete(confirm: boolean) {
    const target = deleting
    if (!target) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      await onDelete(target.company.id, confirm)
      setDeleting(null)
    } catch (failure) {
      const counts = deleteBlockedFrom(failure)
      if (counts) {
        setDeleting({ ...target, counts })
      } else {
        setError(serverErrorMessage(failure))
      }
    } finally {
      setBusy(false)
    }
  }

  const action = canManage ? (
    <Button
      size="sm"
      onClick={() => {
        setEditing(null)
        setDialogOpen(true)
      }}
    >
      Add company
    </Button>
  ) : null

  return (
    <SettingsCard
      title="Companies"
      description="The legal entities this workspace reports on."
      action={action}
    >
      <div className="flex flex-col gap-4">
        <label className="flex items-center gap-3 text-sm">
          <Switch
            checked={includeInactive}
            onCheckedChange={(next: boolean) => onIncludeInactiveChange(next)}
            aria-label="Show inactive companies"
          />
          Show inactive companies
        </label>

        {loading ? (
          <p className="text-sm text-muted-foreground">Loading companies…</p>
        ) : companies.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border p-8 text-center">
            <p className="text-sm font-medium">No companies yet</p>
            <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
              Add the legal entity whose ERP data you want to categorize and
              report on.
            </p>
            {canManage ? (
              <Button
                className="mt-4"
                size="sm"
                onClick={() => {
                  setEditing(null)
                  setDialogOpen(true)
                }}
              >
                Add your first company
              </Button>
            ) : null}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Country</TableHead>
                <TableHead>Currency</TableHead>
                <TableHead>VAT number</TableHead>
                <TableHead>Status</TableHead>
                {canManage ? (
                  <TableHead className="text-right">Actions</TableHead>
                ) : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {companies.map((company) => (
                <TableRow key={company.id}>
                  <TableCell className="font-medium">{company.name}</TableCell>
                  <TableCell>{company.country_code ?? '—'}</TableCell>
                  <TableCell>{company.base_currency}</TableCell>
                  <TableCell>{company.vat_number ?? '—'}</TableCell>
                  <TableCell>
                    <Badge variant={company.is_active ? 'success' : 'default'}>
                      {company.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </TableCell>
                  {canManage ? (
                    <TableCell className="text-right">
                      <div className="flex justify-end">
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            render={
                              <IconButton
                                aria-label={`Actions for ${company.name}`}
                                disabled={busy}
                              >
                                <MoreHorizontal />
                              </IconButton>
                            }
                          />
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => {
                                setEditing(company)
                                setDialogOpen(true)
                              }}
                            >
                              <Pencil />
                              Edit
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              disabled={
                                onManageAccounts === undefined ||
                                integrationsFor(integrations, company.id)
                                  .length === 0
                              }
                              onClick={() => onManageAccounts?.(company.id)}
                            >
                              <ListChecks />
                              Manage accounts
                            </DropdownMenuItem>
                            {onRecomputeFx ? (
                              <DropdownMenuItem
                                onClick={() =>
                                  setRecomputing({
                                    company,
                                    currency: null,
                                    result: null,
                                    busy: false,
                                  })
                                }
                              >
                                <RefreshCw />
                                Recompute currency figures
                              </DropdownMenuItem>
                            ) : null}
                            {onRecategorize ? (
                              <DropdownMenuItem
                                onClick={() => {
                                  setError(null)
                                  setRecategorizing({
                                    company,
                                    result: null,
                                    busy: false,
                                  })
                                }}
                              >
                                <Sparkles />
                                Recategorize failed lines
                              </DropdownMenuItem>
                            ) : null}
                            <DropdownMenuSeparator />
                            {company.is_active ? (
                              <DropdownMenuItem
                                className="text-destructive [&_svg]:text-destructive"
                                onClick={() => {
                                  setError(null)
                                  setConfirming(company.id)
                                }}
                              >
                                <Ban />
                                Deactivate
                              </DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem
                                onClick={() => void toggleActive(company)}
                              >
                                <RotateCcw />
                                Reactivate
                              </DropdownMenuItem>
                            )}
                            {canDelete ? (
                              <DropdownMenuItem
                                className="text-destructive [&_svg]:text-destructive"
                                onClick={() => {
                                  setError(null)
                                  setDeleting({
                                    company,
                                    counts: null,
                                    typed: '',
                                  })
                                }}
                              >
                                <Trash2 />
                                Delete permanently
                              </DropdownMenuItem>
                            ) : null}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {error && confirmingCompany === undefined ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : null}

        {!canManage ? (
          <ReadOnlyNotice>
            Changing companies requires an admin or moderator role.
          </ReadOnlyNotice>
        ) : null}
      </div>

      <DeactivateCompanyDialog
        company={confirmingCompany}
        busy={busy}
        error={error}
        onCancel={() => setConfirming(null)}
        onDismiss={() => {
          setConfirming(null)
          setError(null)
        }}
        onConfirm={(company) => void toggleActive(company)}
      />

      <DeleteCompanyDialog
        state={deleting}
        busy={busy}
        error={error}
        onTypedChange={(typed) =>
          setDeleting((current) => (current ? { ...current, typed } : current))
        }
        onCancel={() => setDeleting(null)}
        onDismiss={() => {
          setDeleting(null)
          setError(null)
        }}
        onConfirm={() => void runDelete(true)}
      />

      <RecomputeDialog
        state={recomputing}
        onClose={() => setRecomputing(null)}
        onRun={runRecompute}
      />

      <RecategorizeDialog
        state={recategorizing}
        onClose={() => setRecategorizing(null)}
        onRun={runRecategorize}
      />

      <StaleLinesDialog
        state={reassigned}
        onClose={() => setReassigned(null)}
        onReview={onReviewStaleLines}
      />

      <ErpSwitchDialog
        state={blocked}
        busy={switchBusy}
        error={switchError}
        onClose={() => {
          setBlocked(null)
          setSwitchError(null)
        }}
        onConfirm={() => void confirmSwitch()}
      />

      {canManage ? (
        <CompanyDialog
          key={`${editing?.id ?? 'new'}-${String(dialogOpen)}`}
          open={dialogOpen}
          company={editing}
          erpTypes={erpTypes}
          erpTypesLoading={erpTypesLoading}
          companyIntegrations={
            editing ? integrationsFor(integrations, editing.id) : []
          }
          spendTrees={spendTrees}
          onOpenChange={setDialogOpen}
          onSubmit={(values) =>
            editing
              ? saveEdits(editing, values)
              : onCreate({
                  name: values.name,
                  country_code: values.country_code,
                  vat_number: values.vat_number,
                  base_currency: values.base_currency,
                  spend_tree_id: values.spend_tree_id,
                  erp_type: values.erp_type,
                  credentials: values.credentials,
                })
          }
        />
      ) : null}
    </SettingsCard>
  )
}
