import * as React from 'react'
import { useForm } from 'react-hook-form'
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
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
  ErpIntegrationRead,
  ErpTypeRead,
  FxRecomputeResult,
  RecategorizeResult,
  CompanyDeleteBlocked,
  ReplaceBlocked,
  SpendTreeRead,
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
  SubmitHandled,
  SubmitRow,
  useSettingsSubmit,
} from './form'

export interface CompanyValues {
  name: string
  country_code: string
  vat_number: string
  /** ISO 4217. Required on create: every figure is presented in it. */
  base_currency: string
  /** The spend tree this company categorizes against. Empty means "the
   *  organization's default", which the server materializes on create. */
  spend_tree_id: string
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
  /**
   * Whether the reader may destroy a company outright — the platform flag, not
   * an org role. Deleting is not offered to anyone else *at all* rather than
   * offered disabled: a disabled control claims a permission that will never
   * be granted.
   */
  canDelete?: boolean
  /** The connectable ERP systems, from `GET /erp-types`. */
  erpTypes?: Array<ErpTypeRead>
  erpTypesLoading?: boolean
  /** Integrations across every company in scope; each dialog picks out its own. */
  integrations?: Array<ErpIntegrationRead>
  /** The organization's active spend trees, for the company's tree picker. */
  spendTrees?: Array<SpendTreeRead>
  onCreate: (values: CompanyCreateValues) => Promise<unknown>
  /** Only the changed fields are sent. */
  onUpdate: (
    id: string,
    changes: Partial<CompanyValues>,
  ) => Promise<{ stale_lines?: number } | unknown>
  /** Open the entries view filtered to the lines a tree change left stale. */
  onReviewStaleLines?: (companyId: string) => void
  /** Only the changed parts are sent; omitting `credentials` keeps the stored secret. */
  onUpdateIntegration?: (
    id: string,
    changes: IntegrationChanges,
  ) => Promise<unknown>
  /**
   * Move a company to a different ERP. Distinct from `onUpdateIntegration`
   * because `PATCH` cannot change `erp_type`: this retires the old integration
   * and starts a new one. Rejects with a 409 carrying the counts it would
   * double until `confirm` is set.
   */
  onReplaceIntegration?: (
    id: string,
    values: {
      erp_type: string
      label: string
      credentials: Record<string, string>
      confirm?: boolean
    },
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
   * Destroy a company and everything it owns. Rejects with the `409` body when
   * the server wants confirming, which `deleteBlockedFrom` reads the counts off.
   */
  onDelete: (id: string, confirm: boolean) => Promise<unknown>
  /**
   * Rewrite a company's stored figures into its current reporting currency.
   * Offered after a currency change and from the row menu; omitting it hides
   * both, for a caller that has no such endpoint.
   */
  onRecomputeFx?: (companyId: string) => Promise<FxRecomputeResult>
  /**
   * Put this company's `ai_failed` lines back in the categorizer's queue
   * (`POST /companies/{id}/recategorize`). Omitting it hides the action.
   *
   * A sibling of `onRecomputeFx` by design: company-scoped maintenance, run
   * after something upstream changed, reporting a count rather than changing
   * what is on screen.
   */
  onRecategorize?: (companyId: string) => Promise<RecategorizeResult>
  /** Navigate to a company's ERP account settings. */
  onManageAccounts?: (companyId: string) => void
}

/**
 * The company's spend tree, chosen from the organization's own.
 *
 * A "default" option is offered exactly when the organization has no template
 * copy yet — choosing it sends no id, which is what makes the server create and
 * assign one. Offered on edit as well as create, because a company that
 * predates spend trees has no tree and creating a new company is not a
 * reasonable way to obtain the default. Suppressed once the copy exists, where
 * it would simply duplicate the entry the list already carries by name.
 */
function SpendTreeField({
  value,
  trees,
  onChange,
}: {
  value: string
  trees: Array<SpendTreeRead>
  onChange: (next: string) => void
}) {
  const items = React.useMemo(
    () => [
      ...(trees.some((tree) => tree.source === 'default_template')
        ? []
        : [{ value: '', label: 'Default spend tree (will be created)' }]),
      ...trees.map((tree) => ({
        value: tree.id,
        label: `${tree.name} (${tree.max_depth} levels)`,
      })),
    ],
    [trees],
  )
  return (
    <Select items={items} value={value} onValueChange={(next) => onChange(String(next))}>
      <SelectTrigger aria-label="Spend tree">
        <SelectValue items={items} />
      </SelectTrigger>
      <SelectContent>
        {items.map((item) => (
          <SelectItem key={item.value || 'default'} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** The recompute prompt: which company, and how far it has got. */
interface RecomputeState {
  company: CompanyRead
  /** Set when the prompt follows a currency change; null when opened directly. */
  currency: string | null
  result: FxRecomputeResult | null
  busy: boolean
}

/** The requeue prompt: which company, and how far it has got. */
interface RecategorizeState {
  company: CompanyRead
  result: RecategorizeResult | null
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
    spend_tree_id: company.spend_tree_id ?? '',
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
    spend_tree_id: values.spend_tree_id,
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

/** The 409 body of a blocked replacement, or null for any other failure.
 *
 * Read off the error's parsed body rather than its message: a count recovered
 * from prose would break on a copy edit.
 */
export function replaceBlockedFrom(err: unknown): ReplaceBlocked | null {
  const body = (err as { body?: { detail?: unknown } } | null)?.body?.detail
  if (!body || typeof body !== 'object') return null
  const detail = body as Partial<ReplaceBlocked>
  return typeof detail.entries === 'number' && typeof detail.invoices === 'number'
    ? (detail as ReplaceBlocked)
    : null
}

/** The 409 body of a blocked deletion, or null for any other failure.
 *
 * Same reasoning as `replaceBlockedFrom`: the figures come off the parsed body,
 * never out of the message, so a copy edit cannot silently empty the dialog.
 */
export function deleteBlockedFrom(err: unknown): CompanyDeleteBlocked | null {
  const body = (err as { body?: { detail?: unknown } } | null)?.body?.detail
  if (!body || typeof body !== 'object') return null
  const detail = body as Partial<CompanyDeleteBlocked>
  return typeof detail.invoices === 'number' && typeof detail.entries === 'number'
    ? (detail as CompanyDeleteBlocked)
    : null
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
 * Ask before putting a company's failed lines back in the categorizer's queue.
 *
 * The wording carries the whole design constraint. The API cannot categorize —
 * the categorizer lives in the AI package and runs only in the sync — so this
 * resets the lines' status and they are picked up on the next run. A dialog
 * promising a result would be a lie with an hour's latency on it, and the user
 * would come back to a screen that looked unchanged and conclude it was broken.
 *
 * Confirmed rather than immediate for the same reason the recompute is: it
 * writes across every invoice of a company, and the count it reports is the
 * only evidence it did anything.
 */
function RecategorizeDialog({
  state,
  onClose,
  onRun,
}: {
  state: RecategorizeState | null
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
              ? result.queued === 0
                ? 'Nothing to queue'
                : 'Queued for the categorizer'
              : `Recategorize ${state?.company.name}’s failed lines?`}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {result ? (
              result.queued === 0 ? (
                // Not "0 lines queued", which reads as work done.
                <>
                  No failed lines were found, so nothing changed. Only lines the
                  AI tried and failed on are eligible.
                </>
              ) : (
                <>
                  {result.queued} lines are queued. They will be categorized on
                  the next sync run — nothing has been categorized yet.
                </>
              )
            ) : (
              <>
                Lines the AI failed on are returned to the queue and categorized
                on the next sync run. Nothing is categorized right now, and
                lines a person has verified are left alone.
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
                {state?.busy ? 'Queueing…' : 'Queue for recategorization'}
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
  // In edit mode the grid is live, so "which connector's fields do we show" is
  // no longer the same question as "which one is connected".
  const switching =
    mode === 'edit' && !!selected && selected !== integration?.erp_type
  const active = erpTypes.find(
    (type) =>
      type.erp_type ===
      (mode === 'edit' && !switching ? integration?.erp_type : selected),
  )
  // Editing without switching: nothing is stored to show, so the inputs appear
  // only once replacement is chosen. Switching: a new integration has no stored
  // credentials at all, so they are simply required.
  const credentialFields = !active
    ? []
    : mode === 'edit' && !switching && !replacing
      ? []
      : active.credential_fields
  // The catalog can lack the connected system — a connector deregistered, or
  // `GET /erp-types` came back empty — in which case the grid has nothing to
  // check. That reads as "no ERP connected", which invites a pick that would
  // actually be a switch, so name what is actually connected wherever the
  // grid cannot.
  const connectedNotOffered =
    mode === 'edit' &&
    !!integration &&
    !switching &&
    !erpTypes.some((type) => type.erp_type === integration.erp_type)

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

              {switching ? null : (
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
              )}
            </>
          ) : null}

          {connectedNotOffered ? (
            <p className="text-sm text-muted-foreground">
              Currently connected to{' '}
              <span className="font-medium text-foreground">
                {integration!.erp_type}
              </span>
              , which is not in the list below.
            </p>
          ) : null}

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
                      // A switch supplies fresh credentials by definition, so
                      // the edit-mode replace flag must not survive it and
                      // then leak into a PATCH if the user selects back.
                      form.setValue('replaceCredentials', false)
                    }}
                  />
                </FormControl>
                {mode === 'edit' ? (
                  <FormDescription>
                    Choosing a different system retires this connection and
                    starts a new one. Nothing already synced is deleted.
                  </FormDescription>
                ) : null}
                <FormMessage />
              </FormItem>
            )}
          />

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
  spendTrees,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  /** The company being edited, or null when creating. */
  company: CompanyRead | null
  erpTypes: Array<ErpTypeRead>
  erpTypesLoading: boolean
  /** The organization's active trees; empty hides the picker entirely. */
  spendTrees: Array<SpendTreeRead>
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
        : {
            name: '',
            country_code: '',
            vat_number: '',
            base_currency: '',
            // Empty means "the organization's default tree", created on the
            // spot by the server if this is its first company.
            spend_tree_id: '',
          }),
      // Seeded in edit mode too: the grid is live there now, and it must open
      // showing what is actually connected rather than nothing selected.
      erp_type: integration?.erp_type ?? preselected?.erp_type ?? '',
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
            {spendTrees.length > 0 ? (
              <FormField
                control={form.control}
                name="spend_tree_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Spend tree</FormLabel>
                    <FormControl>
                      <SpendTreeField
                        value={field.value}
                        trees={spendTrees}
                        onChange={field.onChange}
                      />
                    </FormControl>
                    <FormDescription>
                      {mode === 'create' ? (
                        <>
                          The taxonomy this company&rsquo;s spend is categorized into. Leave it on
                          the default unless you have built your own.
                        </>
                      ) : (
                        <>
                          Changing this keeps every category already assigned on record, but lines
                          whose category is not in the new tree will be marked for review.
                        </>
                      )}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            ) : null}
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
 * Companies. Deactivation is the ordinary way to retire one: it is reversible
 * and keeps every record, and it is what an org manager gets.
 *
 * A platform system admin additionally gets `Delete permanently`, for a company
 * that should not exist — a typo, a trial that never synced, a test tenant, or
 * one a customer asked to have removed. It destroys the ledger and cannot be
 * undone, which is why it is the only action here that asks for the company's
 * name rather than a click.
 */
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
  // The company being destroyed, what the server says it holds, and the name
  // typed back. `counts` is null until the server has refused once — the dialog
  // asks *before* it knows, then re-renders with the figures.
  const [deleting, setDeleting] = React.useState<{
    company: CompanyRead
    counts: CompanyDeleteBlocked | null
    typed: string
  } | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [recomputing, setRecomputing] = React.useState<RecomputeState | null>(
    null,
  )
  const [recategorizing, setRecategorizing] =
    React.useState<RecategorizeState | null>(null)
  const [reassigned, setReassigned] = React.useState<{
    company: CompanyRead
    staleLines: number
  } | null>(null)
  const [blocked, setBlocked] = React.useState<{
    integrationId: string
    values: { erp_type: string; label: string; credentials: Record<string, string> }
    counts: ReplaceBlocked
  } | null>(null)
  // Separate from the panel's shared `error`: that one belongs to the
  // deactivate dialog (guarded by `confirmingCompany`) and to the recompute
  // dialog, neither of which is open while this one is, but conflating them
  // would make each dialog's error read as if it might belong to the other.
  const [switchError, setSwitchError] = React.useState<string | null>(null)
  // Guards `confirmSwitch` against a double-click (or a retry fired while the
  // first request is still in flight): a second `replace` on the same
  // integration would re-stamp `disconnected_at` and provision a *second*
  // live integration, which the sync runner would then treat as two sources
  // and double every entry it posts. The disabled buttons below are the
  // user-facing half of that guard.
  const [switchBusy, setSwitchBusy] = React.useState(false)
  const toast = useToast()

  const confirmingCompany = companies.find(
    (company) => company.id === confirming,
  )

  /**
   * Attempt the switch from inside `saveEdits`. A 409 is not a failure of the
   * save — the company fields already saved above it — so it is reported by
   * opening the confirm dialog and throwing `SubmitHandled`: that stops
   * `useSettingsSubmit` from closing the edit dialog or claiming success,
   * without it also showing a generic "couldn't save" on top of the dialog
   * that already explains what happened. Any other failure is left to
   * propagate and hit the normal path.
   */
  async function saveIntegrationSwitch(
    integrationId: string,
    values: { erp_type: string; label: string; credentials: Record<string, string> },
  ) {
    try {
      await onReplaceIntegration?.(integrationId, values)
    } catch (err) {
      const counts = replaceBlockedFrom(err)
      if (!counts) throw err
      setBlocked({ integrationId, values, counts })
      throw new SubmitHandled()
    }
  }

  /**
   * Re-post with the block acknowledged. This runs from the confirm dialog's
   * own button, outside `saveEdits` and outside `useSettingsSubmit` — by the
   * time it fires, the edit dialog has already handed control to this
   * dialog, so a failure here has nowhere else to surface and is shown right
   * on this dialog rather than becoming a dropped, unhandled rejection.
   */
  async function confirmSwitch() {
    if (!blocked || switchBusy) return
    setSwitchBusy(true)
    try {
      await onReplaceIntegration?.(blocked.integrationId, {
        ...blocked.values,
        confirm: true,
      })
      setBlocked(null)
      setSwitchError(null)
      // This action is the one that just retired an ERP connection, and
      // `setDialogOpen(false)` alone is a weak success signal for that — so
      // it gets its own toast rather than relying on `useSettingsSubmit`'s,
      // which this path bypasses entirely (see the function doc above).
      toast.add({ title: 'ERP switched' })
      // The switch has now actually happened — unlike the initial attempt,
      // there is nothing left pending, so this completes the edit the same
      // way any other successful save would.
      setDialogOpen(false)
    } catch (err) {
      setSwitchError(serverErrorMessage(err))
    } finally {
      setSwitchBusy(false)
    }
  }

  /**
   * Save an edit. The company and its integration are separate resources with
   * no compound endpoint, so this is two requests — each sent only if that part
   * actually changed. A failure of either propagates, so the dialog reports it
   * rather than claiming success.
   */
  async function saveEdits(company: CompanyRead, values: CompanyFormValues) {
    const changes = changedFields(toValues(company), values)
    let result: { stale_lines?: number } | undefined
    if (Object.keys(changes).length > 0) {
      result = (await onUpdate(company.id, changes)) as { stale_lines?: number }
    }
    // A spend-tree change costs something, and the caller has to learn what at
    // the moment they cause it — the count only exists server-side, so it is
    // reported back rather than guessed at before the save.
    if (changes.spend_tree_id !== undefined && (result?.stale_lines ?? 0) > 0) {
      setReassigned({ company, staleLines: result!.stale_lines! })
    }
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

    if (integration && values.erp_type && values.erp_type !== integration.erp_type) {
      // The system itself changed, so this is a replacement, not an edit — the
      // API refuses `erp_type` on a PATCH, and the two are different actions.
      await saveIntegrationSwitch(integration.id, {
        erp_type: values.erp_type,
        label: values.label,
        credentials,
      })
    } else if (integration) {
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

  async function runRecategorize() {
    if (!recategorizing || !onRecategorize) return
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

  /**
   * Destroy the company, or learn what it holds and ask again.
   *
   * The first attempt goes unconfirmed on purpose: the server owns the counts,
   * and asking it is what keeps the dialog's figures true rather than a second
   * client-side tally that could drift from the one doing the deleting.
   */
  async function runDelete(confirm: boolean) {
    const target = deleting
    if (!target) return
    setBusy(true)
    setError(null)
    try {
      await onDelete(target.company.id, confirm)
      setDeleting(null)
    } catch (failure) {
      const counts = deleteBlockedFrom(failure)
      if (counts) {
        // Not an error — the server telling us what to warn about.
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
                            {onRecategorize ? (
                              <DropdownMenuItem
                                onClick={() => {
                                  setError(null) // never open onto a stale failure
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
                            {/* Absent for anyone without the platform flag,
                                never disabled: a greyed-out control claims a
                                permission that will never be granted. */}
                            {canDelete ? (
                              <DropdownMenuItem
                                className="text-destructive [&_svg]:text-destructive"
                                onClick={() => {
                                  setError(null)
                                  setDeleting({ company, counts: null, typed: '' })
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

      {/*
        The only action in the product with no undo, so the only one that asks
        for more than a click. A checkbox is a reflex; typing the name is a
        second look at *which* company — which is the mistake that actually
        happens, since the rest of the dialog looks the same for all of them.
      */}
      <AlertDialog
        open={deleting !== null}
        onOpenChange={(next: boolean) => {
          if (!next && !busy) {
            setDeleting(null)
            setError(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {deleting?.company.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleting?.counts ? (
                <>
                  This destroys {deleting.counts.invoices} invoice
                  {deleting.counts.invoices === 1 ? '' : 's'},{' '}
                  {deleting.counts.lines} line
                  {deleting.counts.lines === 1 ? '' : 's'} and{' '}
                  {deleting.counts.entries} posting
                  {deleting.counts.entries === 1 ? '' : 's'}
                  {deleting.counts.earliest && deleting.counts.latest ? (
                    <>
                      {' '}
                      covering {deleting.counts.earliest} to{' '}
                      {deleting.counts.latest}
                    </>
                  ) : null}
                  . This cannot be undone.
                </>
              ) : (
                <>
                  This destroys the company and everything it owns — invoices,
                  lines and ledger postings. This cannot be undone.
                </>
              )}{' '}
              Deactivate it instead to retire it while keeping the records.
              Suppliers are shared across the platform and are kept either way.
            </AlertDialogDescription>
          </AlertDialogHeader>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm" htmlFor="confirm-company-name">
              Type <span className="font-medium text-foreground">{deleting?.company.name}</span>{' '}
              to confirm
            </label>
            <Input
              id="confirm-company-name"
              aria-label="Confirm the company name"
              autoComplete="off"
              value={deleting?.typed ?? ''}
              onChange={(event) =>
                setDeleting((current) =>
                  current ? { ...current, typed: event.target.value } : current,
                )
              }
            />
          </div>

          {/* Behind the backdrop the panel's own error is invisible, so a
              refusal has to be readable from inside the dialog. */}
          {error ? <p className="text-sm text-destructive">{error}</p> : null}

          <AlertDialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(null)} disabled={busy}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={busy || deleting?.typed.trim() !== deleting?.company.name}
              onClick={() => void runDelete(true)}
            >
              {busy ? 'Deleting…' : 'Delete permanently'}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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

      <AlertDialog
        open={reassigned !== null}
        onOpenChange={(open) => !open && setReassigned(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {reassigned?.staleLines} line
              {reassigned?.staleLines === 1 ? '' : 's'} need reviewing
            </AlertDialogTitle>
            <AlertDialogDescription>
              {reassigned?.company.name}&rsquo;s spend tree changed. Those lines keep the
              categories they were given — nothing was deleted — but those categories are not
              in the new tree, so someone should re-decide them.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button variant="ghost" onClick={() => setReassigned(null)}>
              Later
            </Button>
            {onReviewStaleLines ? (
              <Button
                onClick={() => {
                  onReviewStaleLines(reassigned!.company.id)
                  setReassigned(null)
                }}
              >
                Review them
              </Button>
            ) : null}
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={blocked !== null}
        onOpenChange={(open) => {
          if (!open) {
            setBlocked(null)
            setSwitchError(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Switch ERP anyway?</AlertDialogTitle>
            <AlertDialogDescription>
              The current connection has posted {blocked?.counts.entries} entries
              across {blocked?.counts.invoices} invoices
              {blocked?.counts.earliest && blocked?.counts.latest
                ? `, from ${blocked.counts.earliest} to ${blocked.counts.latest}`
                : ''}
              . None of it is deleted — but the new system will deliver those
              periods again as separate rows, so spend covering them will be
              counted twice in reports.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {/* A rejected retry has to be readable from inside this dialog —
              behind the backdrop, the panel's own error message is invisible
              — the same reasoning as the deactivate dialog's inline error. */}
          {switchError ? (
            <p className="text-sm text-destructive">{switchError}</p>
          ) : null}
          <AlertDialogFooter>
            <Button
              variant="ghost"
              onClick={() => {
                setBlocked(null)
                setSwitchError(null)
              }}
              disabled={switchBusy}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => void confirmSwitch()}
              disabled={switchBusy}
            >
              {switchBusy ? 'Switching…' : 'Switch anyway'}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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
          spendTrees={spendTrees}
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
