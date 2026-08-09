import * as React from 'react'
import { useForm } from 'react-hook-form'
import {
  Ban,
  ListChecks,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  RotateCcw,
} from 'lucide-react'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Button,
  cn,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  IconButton,
  Input,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '#/components/ui'
import type {
  CompanyRead,
  ErpIntegrationRead,
  ErpTypeRead,
  FxRecomputeResult,
} from '#/lib/types'
import { findCountry } from '#/lib/countries'
import { currencyForCountry, findCurrency } from '#/lib/currencies'
import { serverErrorMessage } from '#/lib/form-errors'
import { CountryField } from './country-field'
import { ErpBrandMark } from './erp-brand-mark'
import { CurrencyField } from './currency-field'
import {
  ReadOnlyNotice,
  SettingsCard,
  SubmitRow,
  useSettingsSubmit,
} from './form'

export interface CompanyValues {
  name: string
  country_code: string
  vat_number: string
  /** ISO 4217. Required on create: every figure is presented in it. */
  base_currency: string
}

/**
 * Creating a company also connects its ERP — a company with no integration
 * syncs nothing — so the create form carries the connection alongside the
 * company fields.
 */
export interface CompanyCreateValues extends CompanyValues {
  erp_type: string
  credentials: Record<string, string>
}

/**
 * Everything both dialogs bind to. Which parts are used depends on the mode:
 * create sends `erp_type` + `credentials`, editing an existing integration
 * sends `label` and — only behind `replaceCredentials` — `credentials`.
 */
interface CompanyFormValues extends CompanyCreateValues {
  label: string
  replaceCredentials: boolean
}

/** What `PATCH /erp-integrations/{id}` is asked to change. */
export interface IntegrationChanges {
  label?: string | null
  /** The API stores credentials as one map, so this always replaces all of them. */
  credentials?: Record<string, string>
}

export interface CompaniesPanelProps {
  companies: Array<CompanyRead>
  loading?: boolean
  includeInactive: boolean
  onIncludeInactiveChange: (next: boolean) => void
  canManage: boolean
  /** The connectable ERP systems, from `GET /erp-types`. */
  erpTypes?: Array<ErpTypeRead>
  erpTypesLoading?: boolean
  /** Integrations across every company in scope; each dialog picks out its own. */
  integrations?: Array<ErpIntegrationRead>
  onCreate: (values: CompanyCreateValues) => Promise<unknown>
  /** Only the changed fields are sent. */
  onUpdate: (id: string, changes: Partial<CompanyValues>) => Promise<unknown>
  /** Only the changed parts are sent; omitting `credentials` keeps the stored secret. */
  onUpdateIntegration?: (
    id: string,
    changes: IntegrationChanges,
  ) => Promise<unknown>
  /** Connect an ERP to a company that has none (created before this was required). */
  onConnectIntegration?: (
    companyId: string,
    values: {
      erp_type: string
      label: string
      credentials: Record<string, string>
    },
  ) => Promise<unknown>
  onSetActive: (id: string, active: boolean) => Promise<unknown>
  /**
   * Rewrite a company's stored figures into its current reporting currency.
   * Offered after a currency change and from the row menu; omitting it hides
   * both, for a caller that has no such endpoint.
   */
  onRecomputeFx?: (companyId: string) => Promise<FxRecomputeResult>
  /** Navigate to a company's ERP account settings. */
  onManageAccounts?: (companyId: string) => void
}

/** The recompute prompt: which company, and how far it has got. */
interface RecomputeState {
  company: CompanyRead
  /** Set when the prompt follows a currency change; null when opened directly. */
  currency: string | null
  result: FxRecomputeResult | null
  busy: boolean
}

/**
 * The integration a company's dialog edits: its first connected one. A company
 * with several is an edge case that belongs on a dedicated ERP page, so the
 * dialog edits one and says the others are there.
 */
export function integrationsFor(
  integrations: Array<ErpIntegrationRead>,
  companyId: string,
): Array<ErpIntegrationRead> {
  const own = integrations.filter((row) => row.company_id === companyId)
  // Connected ones first, so a soft-disconnected integration is never the one
  // silently edited while a live one sits behind it.
  return [
    ...own.filter((row) => row.disconnected_at === null),
    ...own.filter((row) => row.disconnected_at !== null),
  ]
}

function toValues(company: CompanyRead): CompanyValues {
  return {
    name: company.name,
    // The one place a non-canonical code can enter the form: the field this
    // replaced was free text, so a row saved as `dk` is entirely possible.
    // Canonicalising on the way in means `before` and `after` agree, so merely
    // opening such a company does not look like an edit — while a code that
    // resolves to nothing is left alone for the validator to catch.
    country_code:
      findCountry(company.country_code)?.code ?? company.country_code ?? '',
    vat_number: company.vat_number ?? '',
    base_currency: company.base_currency,
  }
}

/** The credential inputs start from whatever defaults the connector declares. */
function defaultCredentials(
  erpType: ErpTypeRead | undefined,
): Record<string, string> {
  if (!erpType) return {}
  return Object.fromEntries(
    erpType.credential_fields.map((field) => [field.name, field.default ?? '']),
  )
}

/** Just the company fields — the create form also carries the ERP connection,
 * which is never part of an update. */
function companyFields(values: CompanyValues): CompanyValues {
  return {
    name: values.name,
    country_code: values.country_code,
    vat_number: values.vat_number,
    base_currency: values.base_currency,
  }
}

/** The fields that actually changed, so a PATCH stays a partial update. */
export function changedFields(
  before: CompanyValues,
  after: CompanyValues,
): Partial<CompanyValues> {
  const changes: Partial<CompanyValues> = {}
  for (const key of Object.keys(companyFields(after)) as Array<
    keyof CompanyValues
  >) {
    if (after[key] !== before[key]) changes[key] = after[key]
  }
  return changes
}

/**
 * Offers to rewrite a company's stored figures into its reporting currency.
 *
 * Recomputing is not automatic on a currency change: rewriting a year of
 * postings is an unbounded write the API will not do inside a PATCH. Until it
 * runs, reports show the old currency — visibly, as its own row — so this
 * explains that and offers the fix while the user is still looking at it.
 */
function RecomputeDialog({
  state,
  onClose,
  onRun,
}: {
  state: RecomputeState | null
  onClose: () => void
  onRun: () => void | Promise<void>
}) {
  const result = state?.result

  return (
    <AlertDialog
      open={state !== null}
      onOpenChange={(next: boolean) => {
        if (!next && !state?.busy) onClose()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {result
              ? 'Figures recomputed'
              : `Recompute ${state?.company.name}’s figures?`}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {result ? (
              <>
                {result.converted} converted, {result.unchanged} already
                current, and {result.unconverted} left unconverted — no rate was
                available for those.
              </>
            ) : state?.currency ? (
              <>
                Everything already imported is still stored in the previous
                currency. Recompute to restate it in {state.currency}, each
                amount at the exchange rate from its own transaction date.
              </>
            ) : (
              <>
                Restates every imported amount in {state?.company.base_currency}
                , each at the exchange rate from its own transaction date.
                Amounts already converted are left untouched.
              </>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          {result ? (
            <Button onClick={onClose}>Done</Button>
          ) : (
            <>
              <Button variant="ghost" onClick={onClose} disabled={state?.busy}>
                Not now
              </Button>
              <Button onClick={() => void onRun()} disabled={state?.busy}>
                {state?.busy ? 'Recomputing…' : 'Recompute'}
              </Button>
            </>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/**
 * The ERP connection. The connector list and the inputs under it come from
 * `GET /erp-types`, so a new connector needs no change here.
 *
 * Three modes, differing in what the API lets them change:
 * - `create` — pick a connector and its credentials; both go with the company.
 * - `edit` — the connector is fixed (the API cannot change it); the label is
 *   editable and credentials can only be replaced wholesale.
 * - `connect` — a company that has no integration; the full connect form, but
 *   optional, so saving a name change alone does not connect anything.
 */
/**
 * The connector picker: one card per registered connector.
 *
 * A dropdown of names was adequate with one connector. With several, this is
 * the moment a customer decides whether we support their accounting system, and
 * a row of marks answers that faster than a list of words — so the choice gets
 * the visual weight rather than the field label.
 *
 * Everything shown comes from `GET /api/v1/erp-types`. There is deliberately no
 * connector name, brand string or per-connector branch here: one registered
 * later appears with no change to this file.
 *
 * Built on native radios rather than ARIA. They are one control with one name,
 * so arrow keys, tab order, the accessible group and the checked state all come
 * from the platform and cannot drift from what is painted.
 */
function ErpTypeGrid({
  erpTypes,
  value,
  onSelect,
}: {
  erpTypes: Array<ErpTypeRead>
  value: string
  onSelect: (erpType: string) => void
}) {
  return (
    <div
      role="radiogroup"
      aria-label="ERP system"
      className="grid gap-2 sm:grid-cols-2"
    >
      {erpTypes.map((type) => (
        <label
          key={type.erp_type}
          className="group cursor-pointer"
          data-testid={`erp-type-${type.erp_type}`}
        >
          <input
            type="radio"
            name="erp-type-choice"
            className="peer sr-only"
            value={type.erp_type}
            checked={value === type.erp_type}
            onChange={() => onSelect(type.erp_type)}
          />
          <span
            className={cn(
              'flex h-full items-start gap-3 rounded-lg border border-input bg-card p-3 transition',
              'group-hover:border-ring group-hover:bg-muted/40',
              // Selection has to read differently from hover, not just darker:
              // the ring is what makes a chosen card unambiguous once the
              // pointer is elsewhere.
              'peer-checked:border-primary peer-checked:bg-primary/5 peer-checked:ring-1 peer-checked:ring-primary',
              'peer-focus-visible:ring-2 peer-focus-visible:ring-ring',
            )}
          >
            <ErpBrandMark slug={type.brand_slug} label={type.label} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-foreground">
                {type.label}
              </span>
              {/* Omitted rather than filled with invented text: a connector the
                  catalog describes gets a line, one it doesn't gets none. */}
              {type.description ? (
                <span className="mt-0.5 block text-sm text-muted-foreground">
                  {type.description}
                </span>
              ) : null}
            </span>
          </span>
        </label>
      ))}
    </div>
  )
}

function ErpConnectionFields({
  form,
  erpTypes,
  loading,
  mode,
  integration,
  otherCount,
}: {
  form: ReturnType<typeof useForm<CompanyFormValues>>
  erpTypes: Array<ErpTypeRead>
  loading: boolean
  mode: 'create' | 'edit' | 'connect'
  integration?: ErpIntegrationRead
  otherCount: number
}) {
  const selected = form.watch('erp_type')
  const replacing = form.watch('replaceCredentials')
  const active =
    mode === 'edit'
      ? erpTypes.find((type) => type.erp_type === integration?.erp_type)
      : erpTypes.find((type) => type.erp_type === selected)
  // In edit mode the credential inputs only appear once replacement is chosen —
  // there is nothing stored to show, so they would otherwise sit there empty and
  // imply the connection has none.
  const credentialFields =
    (mode === 'edit' && !replacing) || !active ? [] : active.credential_fields

  return (
    <div className="flex flex-col gap-4 border-t border-border pt-4">
      <div>
        <h3 className="text-sm font-medium">ERP connection</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {mode === 'create'
            ? 'A company without one syncs nothing, so it is connected up front.'
            : mode === 'connect'
              ? 'This company is not connected to an ERP, so it syncs nothing. Connect one to start.'
              : 'Where this company’s ERP data is read from.'}
        </p>
        {otherCount > 0 ? (
          <p className="mt-1 text-sm text-muted-foreground">
            This company has {otherCount} other{' '}
            {otherCount === 1 ? 'integration' : 'integrations'}, managed outside
            this dialog.
          </p>
        ) : null}
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading ERP systems…</p>
      ) : mode !== 'edit' && erpTypes.length === 0 ? (
        <p className="text-sm text-destructive">
          No ERP systems are available to connect. Check the web API
          configuration.
        </p>
      ) : (
        <>
          {mode === 'edit' && integration ? (
            <>
              {/* Static: the API offers no way to change an integration's type. */}
              <div>
                <p className="text-sm font-medium">ERP system</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {erpTypes.find((t) => t.erp_type === integration.erp_type)
                    ?.label ?? integration.erp_type}{' '}
                  — connecting a different system replaces the integration,
                  which is not done from here.
                </p>
              </div>

              <FormField
                control={form.control}
                name="label"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Connection label (optional)</FormLabel>
                    <FormControl>
                      <Input placeholder="Main" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex flex-col gap-2">
                <label className="flex items-center gap-3 text-sm">
                  <Switch
                    checked={replacing}
                    onCheckedChange={(next: boolean) => {
                      form.setValue('replaceCredentials', next)
                      // Start from the connector's defaults each time it is
                      // switched on — there is nothing stored to restore.
                      form.setValue(
                        'credentials',
                        next
                          ? defaultCredentials(
                              erpTypes.find(
                                (t) => t.erp_type === integration.erp_type,
                              ),
                            )
                          : {},
                      )
                    }}
                    aria-label="Replace credentials"
                  />
                  Replace credentials
                </label>
                <p className="text-sm text-muted-foreground">
                  {integration.has_credentials
                    ? 'Credentials are set. They are never shown, so replacing them means entering every field again.'
                    : 'No credentials are stored; the connector falls back to its defaults.'}
                </p>
              </div>
            </>
          ) : null}

          {mode === 'edit' ? null : (
            <FormField
              control={form.control}
              name="erp_type"
              // Optional when connecting an existing company: saving a name
              // change alone must not silently connect an ERP.
              rules={
                mode === 'create'
                  ? { required: 'Choose an ERP system.' }
                  : undefined
              }
              render={({ field }) => (
                <FormItem>
                  <FormLabel>ERP system</FormLabel>
                  <FormControl>
                    <ErpTypeGrid
                      erpTypes={erpTypes}
                      value={field.value}
                      onSelect={(next) => {
                        field.onChange(next)
                        // Reseed the inputs from the newly chosen connector's defaults.
                        form.setValue(
                          'credentials',
                          defaultCredentials(
                            erpTypes.find((t) => t.erp_type === next),
                          ),
                        )
                      }}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          {mode === 'connect' && active ? (
            <FormField
              control={form.control}
              name="label"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Connection label (optional)</FormLabel>
                  <FormControl>
                    <Input placeholder="Main" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          ) : null}

          {credentialFields.map((credential) => (
            <FormField
              key={credential.name}
              control={form.control}
              name={`credentials.${credential.name}` as const}
              rules={
                credential.required
                  ? {
                      validate: (value: string) =>
                        value.trim().length > 0 ||
                        `Enter the ${credential.label.toLowerCase()}.`,
                    }
                  : undefined
              }
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {credential.label}
                    {credential.required ? '' : ' (optional)'}
                  </FormLabel>
                  <FormControl>
                    <Input
                      type={credential.secret ? 'password' : 'text'}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          ))}
        </>
      )}
    </div>
  )
}

function CompanyDialog({
  open,
  company,
  erpTypes,
  erpTypesLoading,
  companyIntegrations,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  /** The company being edited, or null when creating. */
  company: CompanyRead | null
  erpTypes: Array<ErpTypeRead>
  erpTypesLoading: boolean
  /** This company's integrations, most-connected first. Empty when creating. */
  companyIntegrations: Array<ErpIntegrationRead>
  onOpenChange: (open: boolean) => void
  onSubmit: (values: CompanyFormValues) => Promise<unknown>
}) {
  const integration = company ? companyIntegrations[0] : undefined
  const mode = !company ? 'create' : integration ? 'edit' : 'connect'
  // With a single connector registered there is nothing to choose, so it is
  // preselected — but only when a connection is required. Connecting from the
  // edit dialog is optional, so nothing is chosen until the user chooses it.
  const soleType = erpTypes.length === 1 ? erpTypes[0] : undefined
  const preselected = mode === 'create' ? soleType : undefined
  const form = useForm<CompanyFormValues>({
    defaultValues: {
      ...(company
        ? toValues(company)
        : { name: '', country_code: '', vat_number: '', base_currency: '' }),
      erp_type: preselected?.erp_type ?? '',
      // Credentials are write-only, so an edit form has nothing to prefill.
      credentials: defaultCredentials(preselected),
      label: integration?.label ?? '',
      replaceCredentials: false,
    },
  })
  const submit = useSettingsSubmit()

  // A country implies a likely reporting currency, so offer it — but only as a
  // pre-selection, and only until the user picks one themselves. A Danish
  // subsidiary reporting in EUR is ordinary; guessing over a deliberate choice
  // would be worse than not guessing at all.
  const countryCode = form.watch('country_code')
  const currencyTouched = form.formState.dirtyFields.base_currency
  React.useEffect(() => {
    if (mode !== 'create' || currencyTouched) return
    const implied = currencyForCountry(countryCode)
    if (implied) form.setValue('base_currency', implied)
  }, [countryCode, currencyTouched, mode, form])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{company ? 'Edit company' : 'Add company'}</DialogTitle>
          <DialogDescription>
            A company is a legal entity whose ERP data this workspace reports
            on.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            className="flex flex-col gap-4"
            onSubmit={submit({
              form,
              run: async (values) => {
                const result = await onSubmit(values)
                onOpenChange(false)
                return result
              },
              success: company ? 'Company updated' : 'Company added',
            })}
          >
            <FormField
              control={form.control}
              name="name"
              rules={{ required: 'Enter a name.' }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="country_code"
                rules={{
                  // Optional, but not free: a code that names no country would
                  // be displayed back in the table and would silently produce
                  // no currency suggestion.
                  validate: (value: string) =>
                    !value ||
                    findCountry(value) !== undefined ||
                    'Choose a country from the list.',
                }}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Country</FormLabel>
                    <FormControl>
                      <CountryField
                        value={field.value}
                        onChange={field.onChange}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="vat_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>VAT number</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="base_currency"
              rules={{
                required: 'Choose a reporting currency.',
                validate: (value: string) =>
                  findCurrency(value) !== undefined ||
                  'Choose a currency from the list.',
              }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Reporting currency</FormLabel>
                  <FormControl>
                    <CurrencyField
                      value={field.value}
                      onChange={field.onChange}
                    />
                  </FormControl>
                  <FormDescription>
                    Every figure for this company is shown in this currency.
                    Amounts posted in another are converted at the rate on the
                    day of the transaction.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <ErpConnectionFields
              form={form}
              erpTypes={erpTypes}
              loading={erpTypesLoading}
              mode={mode}
              integration={integration}
              otherCount={Math.max(companyIntegrations.length - 1, 0)}
            />
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <SubmitRow
                form={form}
                label={company ? 'Save changes' : 'Add company'}
              />
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Companies. They are soft-deactivated and never hard-deleted, so no delete
 * action is offered anywhere.
 */
export function CompaniesPanel({
  companies,
  loading = false,
  includeInactive,
  onIncludeInactiveChange,
  canManage,
  erpTypes = [],
  erpTypesLoading = false,
  integrations = [],
  onCreate,
  onUpdate,
  onUpdateIntegration,
  onConnectIntegration,
  onSetActive,
  onRecomputeFx,
  onManageAccounts,
}: CompaniesPanelProps) {
  const [dialogOpen, setDialogOpen] = React.useState(false)
  const [editing, setEditing] = React.useState<CompanyRead | null>(null)
  const [confirming, setConfirming] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [recomputing, setRecomputing] = React.useState<RecomputeState | null>(
    null,
  )

  const confirmingCompany = companies.find(
    (company) => company.id === confirming,
  )

  /**
   * Save an edit. The company and its integration are separate resources with
   * no compound endpoint, so this is two requests — each sent only if that part
   * actually changed. A failure of either propagates, so the dialog reports it
   * rather than claiming success.
   */
  async function saveEdits(company: CompanyRead, values: CompanyFormValues) {
    const changes = changedFields(toValues(company), values)
    if (Object.keys(changes).length > 0) await onUpdate(company.id, changes)
    // Changing the reporting currency does not rewrite what is already stored —
    // the API refuses to do an unbounded write inside a PATCH — so the figures
    // stay in the old currency until a recompute. Say so while the user is
    // still here, rather than letting them find out from a stale report.
    if (changes.base_currency && onRecomputeFx) {
      setRecomputing({
        company,
        currency: changes.base_currency,
        result: null,
        busy: false,
      })
    }

    const [integration] = integrationsFor(integrations, company.id)
    // Blank inputs are dropped so the connector falls back to its own defaults
    // rather than storing empty strings.
    const credentials = Object.fromEntries(
      Object.entries(values.credentials).filter(
        ([, value]) => value.trim() !== '',
      ),
    )

    if (integration) {
      const integrationChanges: IntegrationChanges = {}
      if ((integration.label ?? '') !== values.label)
        integrationChanges.label = values.label
      // Omitted unless replacement was explicitly chosen — sending it at all
      // would overwrite the stored secret.
      if (values.replaceCredentials)
        integrationChanges.credentials = credentials
      if (Object.keys(integrationChanges).length > 0) {
        await onUpdateIntegration?.(integration.id, integrationChanges)
      }
    } else if (values.erp_type) {
      // Connecting is optional here, so it happens only once a system is chosen.
      await onConnectIntegration?.(company.id, {
        erp_type: values.erp_type,
        label: values.label,
        credentials,
      })
    }
  }

  async function runRecompute() {
    if (!recomputing || !onRecomputeFx) return
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
            // Base UI passes an event detail second; the contract is the flag alone.
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
                                // Named per row: a screen reader hearing a dozen
                                // "Actions" buttons cannot tell them apart.
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
                            {/* Navigation is a callback, not a `Link`: this
                                panel is presentational and rendered directly in
                                tests, where there is no RouterProvider.
                                Disabled without a connection — there is no
                                chart of accounts to manage. */}
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
                            <DropdownMenuSeparator />
                            {company.is_active ? (
                              <DropdownMenuItem
                                className="text-destructive [&_svg]:text-destructive"
                                // Destructive and not trivially undone for a
                                // company that owns financial data, so it asks.
                                onClick={() => {
                                  setError(null) // never open onto a stale failure
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

        {/* Only when the confirm dialog is closed — it shows the error itself,
            and rendering it twice would state the same thing in two places. */}
        {error && confirmingCompany === undefined ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : null}

        {!canManage ? (
          <ReadOnlyNotice>
            Changing companies requires an admin or moderator role.
          </ReadOnlyNotice>
        ) : null}
      </div>

      {/* Deactivation is confirmed in its own dialog rather than by swapping
          buttons into the row, so the consequence can actually be stated. */}
      <AlertDialog
        open={confirmingCompany !== undefined}
        onOpenChange={(next: boolean) => {
          if (!next) {
            setConfirming(null)
            setError(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Deactivate {confirmingCompany?.name}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              It stops appearing in the default company list and syncs nothing
              further. Its invoices and ledger entries are kept, and you can
              reactivate it at any time.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {/* A rejection has to be readable from inside the dialog — behind the
              backdrop, the panel's own error message is invisible. */}
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <AlertDialogFooter>
            <Button
              variant="ghost"
              onClick={() => setConfirming(null)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() =>
                confirmingCompany && void toggleActive(confirmingCompany)
              }
            >
              {busy ? 'Deactivating…' : 'Deactivate'}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <RecomputeDialog
        state={recomputing}
        onClose={() => setRecomputing(null)}
        onRun={runRecompute}
      />

      {canManage ? (
        <CompanyDialog
          // Remounts per opening, so the form is always seeded from what it is
          // editing rather than from a previous, abandoned edit.
          key={`${editing?.id ?? 'new'}-${String(dialogOpen)}`}
          open={dialogOpen}
          company={editing}
          erpTypes={erpTypes}
          erpTypesLoading={erpTypesLoading}
          companyIntegrations={
            editing ? integrationsFor(integrations, editing.id) : []
          }
          onOpenChange={setDialogOpen}
          onSubmit={(values) =>
            editing
              ? saveEdits(editing, values)
              : // The create contract carries no label or replace flag — those
                // are edit-mode form state, not part of the request.
                onCreate({
                  name: values.name,
                  country_code: values.country_code,
                  vat_number: values.vat_number,
                  base_currency: values.base_currency,
                  erp_type: values.erp_type,
                  credentials: values.credentials,
                })
          }
        />
      ) : null}
    </SettingsCard>
  )
}
