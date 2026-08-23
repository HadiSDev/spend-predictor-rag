import * as React from 'react'
import { Trash2 } from 'lucide-react'
import {
  Button,
  CurrencyInput,
  Field,
  FieldControl,
  FieldLabel,
  NumberInput,
  Progress,
} from '#/components/ui'
import { TreeSelector } from '#/components/spend-tree/tree-selector'
import { LineStatusBadge } from './line-status'
import { formatMoney, toNumber } from '#/lib/format'
import { serverErrorMessage } from '#/lib/form-errors'
import type {
  InvoiceLineRead,
  InvoiceLineUpdate,
  LineCorrections,
  SpendCategoryRead,
} from '#/lib/types'

/** Re-exported for existing importers (`voucher-details-tab.tsx`,
 *  `voucher-drawer.tsx`) — the canonical definition now lives in
 *  `lib/types.ts` alongside the other API-shape types, so `lib/invoices.ts`
 *  (a mutation, not a component) can use it without importing a component. */
export type { LineCorrections }

export interface LineEditorProps {
  line: InvoiceLineRead
  /** The invoice's currency — a line carries no currency of its own. */
  currency: string | null
  /** The company's spend tree, flat and shallowest-first. Null while it loads;
   *  empty when the company has no tree assigned. */
  nodes: Array<SpendCategoryRead> | null
  /** Where a manager assigns the company's tree, for the no-tree case. */
  companySettingsHref?: string
  /** Whether the reader may write. A `viewer` sees the line's values as text
   *  and gets neither the category selector's actions nor delete. */
  canManage: boolean
  /** Sending an empty object accepts the AI result as-is (`verify`, not `edit`). */
  onVerify: (lineId: string, corrections: LineCorrections) => Promise<void>
  /** Correct what the line says was bought (`PATCH /invoice-lines/{id}`). A
   *  separate call from `onVerify`: the category is resolved against the
   *  company's tree, these are values read off a document. */
  onUpdate: (lineId: string, changes: InvoiceLineUpdate) => Promise<void>
  /** Delete the line (`DELETE /invoice-lines/{id}`). Omit to hide the control. */
  onDelete?: (lineId: string) => Promise<void>
}

/** The path a line's stored levels describe, trailing levels dropped. */
function storedPath(line: InvoiceLineRead): Array<string> {
  return [line.level_1, line.level_2, line.level_3, line.level_4].filter(
    (value): value is string => value !== null && value !== '',
  )
}

/**
 * What a human may say a line was, beside the category.
 *
 * **The numeric fields hold numbers, not the text in their inputs.** They used
 * to hold strings, converted on save with `Number(value)` — and `Number('1,5')`
 * is `NaN`, which serializes to JSON `null`, which the API reads as "clear this
 * field". A reviewer typing a European decimal erased the figure and was told
 * nothing. The typed controls parse as the user types, so an unreadable figure
 * never becomes a value at all.
 *
 * Holding parsed numbers is also what keeps "dirty" honest: the formatter
 * rewrites a stored `1234.50000` as `1,234.50` on mount, and a string-based
 * comparison would call that an edit and prompt about unsaved work nobody did.
 */
interface LineValues {
  item_name: string
  description: string
  quantity: number | null
  unit: string
  unit_price: number | null
  amount: number | null
}

const LINE_TEXT_FIELDS = ['item_name', 'description', 'unit'] as const
const LINE_NUMBER_FIELDS = ['quantity', 'unit_price', 'amount'] as const

/** A stored Decimal-as-string as a number, or null when it is unset or unreadable. */
function money(value: InvoiceLineRead['amount']): number | null {
  if (value === null || value === undefined) return null
  const parsed = toNumber(value)
  return Number.isNaN(parsed) ? null : parsed
}

function lineValuesFrom(line: InvoiceLineRead): LineValues {
  return {
    item_name: line.item_name ?? '',
    description: line.description ?? '',
    quantity: money(line.quantity),
    unit: line.unit ?? '',
    unit_price: money(line.unit_price),
    amount: money(line.amount),
  }
}

function toLineUpdate(current: LineValues, original: LineValues): InvoiceLineUpdate {
  const changes: InvoiceLineUpdate = {}
  for (const field of LINE_TEXT_FIELDS) {
    // An emptied text field is an explicit null, which is a correction: a
    // reviewer splitting a stand-in may legitimately have nothing to name.
    if (current[field] !== original[field]) changes[field] = current[field] || null
  }
  for (const field of LINE_NUMBER_FIELDS) {
    // Already a number or null — nothing to parse, so nothing to misparse.
    if (current[field] !== original[field]) changes[field] = current[field]
  }
  return changes
}

/**
 * One line: what was bought, and the category assigned to it — both correctable.
 *
 * The two are saved by different calls, and deliberately so. A category is
 * *chosen* from the company's tree and the server derives the levels from the
 * chosen node's path, because a typed level matching no node produces a
 * categorization resolving to nothing — the silent failure the stored
 * `spend_category_id` exists to prevent. The values beside it are free text a
 * human read off a document, and go through the line's own PATCH, which refuses
 * a category outright rather than ignoring it.
 */
export function LineEditor({
  line,
  currency,
  nodes,
  companySettingsHref,
  canManage,
  onVerify,
  onUpdate,
  onDelete,
}: LineEditorProps) {
  // Recomputed from the line every render, so a fresh server value (after a
  // save) is picked up without a synchronizing effect — only `chosen` below is
  // state the user's own action owns.
  const [chosen, setChosen] = React.useState<SpendCategoryRead | null>(null)
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [confirmingDelete, setConfirmingDelete] = React.useState(false)

  // Same baseline-as-state discipline the header editor uses: a successful save
  // updates it immediately, so "dirty" clears the instant the save resolves
  // rather than waiting on the detail query to refetch.
  const [savedValues, setSavedValues] = React.useState<LineValues>(() => lineValuesFrom(line))
  const [values, setValues] = React.useState<LineValues>(savedValues)

  const selectedId = chosen?.id ?? line.spend_category_id
  const categoryDirty = chosen !== null && chosen.id !== line.spend_category_id
  const valuesDirty = [...LINE_TEXT_FIELDS, ...LINE_NUMBER_FIELDS].some(
    (f) => values[f] !== savedValues[f],
  )

  function setValue<K extends keyof LineValues>(field: K, value: LineValues[K]) {
    setValues((current) => ({ ...current, [field]: value }))
  }

  function handleCancel() {
    setChosen(null)
    setValues(savedValues)
    setError(null)
  }

  async function run(action: () => Promise<void>) {
    setSubmitting(true)
    setError(null)
    try {
      await action()
      return true
    } catch (failure) {
      setError(serverErrorMessage(failure))
      return false
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSaveValues() {
    const changes = toLineUpdate(values, savedValues)
    if (await run(() => onUpdate(line.id, changes))) setSavedValues(values)
  }

  async function handleAccept() {
    // Only the node — the server takes the levels from its path, so a
    // correction cannot store a category that resolves to nothing.
    const corrections: LineCorrections = categoryDirty
      ? { spend_category_id: chosen!.id }
      : {}
    if (await run(() => onVerify(line.id, corrections))) setChosen(null)
  }

  async function handleDelete() {
    if (onDelete === undefined) return
    await run(() => onDelete(line.id))
  }

  const confidencePct =
    line.confidence === null ? null : Math.round(toNumber(line.confidence) * 100)
  const stale = line.category_stale
  const previous = storedPath(line)

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">
            {line.description ?? 'Untitled line'}
          </p>
          <p className="text-sm tabular-nums text-muted-foreground">
            {line.amount !== null ? formatMoney(line.amount, currency) : '—'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Shared with the Entries table's Status column, so the two views
              cannot drift into describing the same line differently. */}
          <LineStatusBadge line={line} />
          {canManage && onDelete !== undefined ? (
            <Button
              size="sm"
              variant="ghost"
              disabled={submitting}
              // Named by position rather than by description: the description
              // is also the category selector's own label on this row, and two
              // controls answering to the same name is a control a screen-reader
              // user cannot address. The confirmation that follows names it.
              aria-label={`Delete line ${line.sequence + 1}`}
              onClick={() => setConfirmingDelete(true)}
            >
              <Trash2 className="size-4" aria-hidden />
            </Button>
          ) : null}
        </div>
      </div>

      {confirmingDelete ? (
        // Named, not a bare "are you sure?": the line carries a categorization
        // a human may have verified, and the audit row is the only place it
        // survives. Inline rather than a modal, so the row it refers to stays
        // on screen while the question is being answered.
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2">
          <p className="text-sm text-foreground">
            Delete <span className="font-medium">{line.description ?? 'this line'}</span>?
            Its postings stay on the voucher.
          </p>
          <div className="ml-auto flex items-center gap-2">
            <Button
              size="sm"
              variant="destructive"
              disabled={submitting}
              onClick={() => void handleDelete()}
            >
              Delete line
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirmingDelete(false)}>
              Keep
            </Button>
          </div>
        </div>
      ) : null}

      {canManage ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {/* The name first, because it is what the line *is*. Every line is
              expected to carry one; the prose below it is what a supplier
              printed sometimes. */}
          <Field className="sm:col-span-2">
            <FieldLabel>Item name</FieldLabel>
            <FieldControl
              value={values.item_name}
              placeholder="What was bought"
              onChange={(event) => setValue('item_name', event.target.value)}
            />
          </Field>
          <Field className="sm:col-span-2">
            <FieldLabel>Description</FieldLabel>
            <FieldControl
              value={values.description}
              placeholder="Any further detail the document printed"
              onChange={(event) => setValue('description', event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Quantity</FieldLabel>
            {/* Four decimals, matching the `Numeric(12,4)` it is stored in, and
                not fixed — `12` should read as `12`. Clamping this to 2 would
                round a stored 0.1250 on save: a data change nobody asked for,
                caused by opening a line and pressing Save. */}
            <NumberInput
              aria-label="Quantity"
              value={values.quantity ?? ''}
              onValueChange={(v) => setValue('quantity', v.floatValue ?? null)}
              thousandSeparator=","
              decimalScale={4}
              inputMode="decimal"
              className="text-right tabular-nums"
            />
          </Field>
          <Field>
            <FieldLabel>Unit</FieldLabel>
            {/* Never defaulted to "pcs": twelve of an unstated unit against
                "Consulting" is twelve hours or twelve days, and a guess here is
                a wrong figure presented with confidence. */}
            <FieldControl
              value={values.unit}
              placeholder="pcs, hours…"
              onChange={(event) => setValue('unit', event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Unit price</FieldLabel>
            {/* Money, but stored at four decimals — a per-unit price genuinely
                carries more precision than a total does. Shown at 2 by the
                currency control, accepting up to 4. */}
            <CurrencyInput
              aria-label="Unit price"
              currency={currency}
              value={values.unit_price}
              onChange={(value) => setValue('unit_price', value)}
              decimalScale={4}
              fixedDecimalScale={false}
            />
          </Field>
          <Field>
            <FieldLabel>Amount</FieldLabel>
            <CurrencyInput
              aria-label="Amount"
              currency={currency}
              value={values.amount}
              onChange={(value) => setValue('amount', value)}
            />
          </Field>
        </div>
      ) : null}

      {nodes === null ? (
        <p className="text-sm text-muted-foreground">Loading the spend tree…</p>
      ) : nodes.length === 0 ? (
        <NoTreeNotice href={companySettingsHref} previous={previous} />
      ) : (
        <Field>
          <FieldLabel>Spend category</FieldLabel>
          <TreeSelector
            nodes={nodes}
            value={selectedId}
            onChange={setChosen}
            placeholder={stale ? 'Choose a category in the current tree' : 'Choose a category'}
            previousPath={stale ? previous : null}
          />
        </Field>
      )}

      {stale && previous.length > 0 && nodes !== null && nodes.length > 0 ? (
        <p className="text-sm text-muted-foreground">
          Previously categorized as{' '}
          <span className="font-medium text-foreground">{previous.join(' › ')}</span>, which is
          not in this company&rsquo;s current spend tree.
        </p>
      ) : null}

      {confidencePct === null ? (
        <p className="text-sm text-muted-foreground">Confidence not available.</p>
      ) : (
        <Progress value={confidencePct} label="Confidence" showValue />
      )}

      {line.rationale ? (
        <p className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
          {line.rationale}
        </p>
      ) : null}

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {canManage ? (
        <div className="flex flex-wrap items-center gap-2">
          {/* Two saves, because they are two different statements: the values
              are what the document said, the category is a decision about them.
              Collapsing them into one button would verify a categorization the
              reviewer had not looked at, just because they fixed a typo. */}
          <Button
            size="sm"
            variant="outline"
            disabled={submitting || !valuesDirty}
            onClick={() => void handleSaveValues()}
          >
            {submitting ? 'Saving…' : 'Save line'}
          </Button>
          <Button size="sm" disabled={submitting} onClick={() => void handleAccept()}>
            {submitting
              ? 'Accepting…'
              : categoryDirty
                ? 'Save & verify category'
                : 'Accept category'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={submitting || !(categoryDirty || valuesDirty)}
            onClick={handleCancel}
          >
            Cancel
          </Button>
        </div>
      ) : null}
    </div>
  )
}

/**
 * No tree assigned. Says so and points at where it is fixed — rather than an
 * empty picker, which claims a choice exists, or free-text inputs, which would
 * reintroduce the very failure the selector removes.
 */
function NoTreeNotice({
  href,
  previous,
}: {
  href?: string
  previous: Array<string>
}) {
  return (
    <div className="rounded-md border border-dashed border-border px-3 py-3 text-sm">
      <p className="text-foreground">No spend tree is assigned to this company.</p>
      <p className="mt-1 text-muted-foreground">
        A category can be chosen once a manager assigns one
        {href ? (
          <>
            {' '}
            in{' '}
            <a href={href} className="font-medium text-primary underline-offset-2 hover:underline">
              company settings
            </a>
          </>
        ) : null}
        .
      </p>
      {previous.length > 0 ? (
        <p className="mt-2 text-muted-foreground">
          Previously categorized as{' '}
          <span className="font-medium text-foreground">{previous.join(' › ')}</span>.
        </p>
      ) : null}
    </div>
  )
}
