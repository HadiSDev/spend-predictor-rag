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
import { formatMoney, toNumber } from '#/lib/format/format'
import { serverErrorMessage } from '#/lib/form-errors'
import type {
  InvoiceLineRead,
  InvoiceLineUpdate,
  LineCorrections,
  SpendCategoryRead,
} from '#/lib/api/types'

export type { LineCorrections }

export interface LineEditorProps {
  line: InvoiceLineRead
  /** The invoice's currency. */
  currency: string | null
  /** The company's spend tree, flat; null while loading. */
  nodes: Array<SpendCategoryRead> | null
  /** Where a manager assigns the company's spend tree. */
  companySettingsHref?: string
  /** Whether the reader may write. */
  canManage: boolean
  /** An empty object accepts the AI result as-is. */
  onVerify: (lineId: string, corrections: LineCorrections) => Promise<void>
  /** Correct what the line says was bought. */
  onUpdate: (lineId: string, changes: InvoiceLineUpdate) => Promise<void>
  /** Reports whether the line has unsaved edits. */
  onDirtyChange?: (dirty: boolean) => void
  /** Delete the line; omit to hide the control. */
  onDelete?: (lineId: string) => Promise<void>
}

/** The category path a line's stored levels describe. */
function storedPath(line: InvoiceLineRead): Array<string> {
  return [line.level_1, line.level_2, line.level_3, line.level_4].filter(
    (value): value is string => value !== null && value !== '',
  )
}

/** The editable values of a line, beside its category. */
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

/** A stored decimal string as a number, or null when unset or unreadable. */
function money(value: InvoiceLineRead['amount']): number | null {
  if (value === null || value === undefined) {
    return null
  }
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

function toLineUpdate(
  current: LineValues,
  original: LineValues,
): InvoiceLineUpdate {
  const changes: InvoiceLineUpdate = {}
  for (const field of LINE_TEXT_FIELDS) {
    if (current[field] !== original[field]) {
      changes[field] = current[field] || null
    }
  }
  for (const field of LINE_NUMBER_FIELDS) {
    if (current[field] !== original[field]) {
      changes[field] = current[field]
    }
  }
  return changes
}

/** Editor for one line's values and category. */
export function LineEditor({
  line,
  currency,
  nodes,
  companySettingsHref,
  canManage,
  onVerify,
  onUpdate,
  onDelete,
  onDirtyChange,
}: LineEditorProps) {
  const [chosen, setChosen] = React.useState<SpendCategoryRead | null>(null)
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [confirmingDelete, setConfirmingDelete] = React.useState(false)

  const [savedValues, setSavedValues] = React.useState<LineValues>(() =>
    lineValuesFrom(line),
  )
  const [values, setValues] = React.useState<LineValues>(savedValues)

  const selectedId = chosen?.id ?? line.spend_category_id
  const categoryDirty = chosen !== null && chosen.id !== line.spend_category_id
  const valuesDirty = [...LINE_TEXT_FIELDS, ...LINE_NUMBER_FIELDS].some(
    (f) => values[f] !== savedValues[f],
  )

  React.useEffect(() => {
    onDirtyChange?.(valuesDirty)
    return () => onDirtyChange?.(false)
  }, [valuesDirty, onDirtyChange])

  function setValue<K extends keyof LineValues>(
    field: K,
    value: LineValues[K],
  ) {
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
    if (await run(() => onUpdate(line.id, changes))) {
      setSavedValues(values)
    }
  }

  async function handleAccept() {
    const corrections: LineCorrections = categoryDirty
      ? { spend_category_id: chosen.id }
      : {}
    if (await run(() => onVerify(line.id, corrections))) {
      setChosen(null)
    }
  }

  async function handleDelete() {
    if (onDelete === undefined) {
      return
    }
    await run(() => onDelete(line.id))
  }

  const confidencePct =
    line.confidence === null
      ? null
      : Math.round(toNumber(line.confidence) * 100)
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
          <LineStatusBadge line={line} />
          {canManage && onDelete !== undefined ? (
            <Button
              size="sm"
              variant="ghost"
              disabled={submitting}
              aria-label={`Delete line ${line.sequence + 1}`}
              onClick={() => setConfirmingDelete(true)}
            >
              <Trash2 className="size-4" aria-hidden />
            </Button>
          ) : null}
        </div>
      </div>

      {confirmingDelete ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2">
          <p className="text-sm text-foreground">
            Delete{' '}
            <span className="font-medium">
              {line.description ?? 'this line'}
            </span>
            ? Its postings stay on the voucher.
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
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setConfirmingDelete(false)}
            >
              Keep
            </Button>
          </div>
        </div>
      ) : null}

      {canManage ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
            <NumberInput
              aria-label="Quantity"
              value={values.quantity ?? ''}
              onValueChange={(v) => setValue('quantity', v.floatValue ?? null)}
              thousandSeparator=","
              decimalScale={4}
              inputMode="decimal"
              className="text-right font-mono tabular-nums"
            />
          </Field>
          <Field>
            <FieldLabel>Unit</FieldLabel>
            <FieldControl
              value={values.unit}
              placeholder="pcs, hours…"
              onChange={(event) => setValue('unit', event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Unit price</FieldLabel>
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
            placeholder={
              stale
                ? 'Choose a category in the current tree'
                : 'Choose a category'
            }
            previousPath={stale ? previous : null}
          />
        </Field>
      )}

      {stale && previous.length > 0 && nodes !== null && nodes.length > 0 ? (
        <p className="text-sm text-muted-foreground">
          Previously categorized as{' '}
          <span className="font-medium text-foreground">
            {previous.join(' › ')}
          </span>
          , which is not in this company&rsquo;s current spend tree.
        </p>
      ) : null}

      {confidencePct === null ? (
        <p className="text-sm text-muted-foreground">
          Confidence not available.
        </p>
      ) : (
        <Progress value={confidencePct} label="Confidence" showValue />
      )}

      {line.rationale && line.status !== 'uncategorized' ? (
        <p className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
          {line.rationale}
        </p>
      ) : null}

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {canManage ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={submitting || !valuesDirty}
            onClick={() => void handleSaveValues()}
          >
            {submitting ? 'Saving…' : 'Save line'}
          </Button>
          <Button
            size="sm"
            disabled={submitting}
            onClick={() => void handleAccept()}
          >
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

/** Shown when the company has no spend tree assigned. */
function NoTreeNotice({
  href,
  previous,
}: {
  href?: string
  previous: Array<string>
}) {
  return (
    <div className="rounded-md border border-dashed border-border px-3 py-3 text-sm">
      <p className="text-foreground">
        No spend tree is assigned to this company.
      </p>
      <p className="mt-1 text-muted-foreground">
        A category can be chosen once a manager assigns one
        {href ? (
          <>
            {' '}
            in{' '}
            <a
              href={href}
              className="font-medium text-foreground underline underline-offset-2 hover:decoration-2"
            >
              company settings
            </a>
          </>
        ) : null}
        .
      </p>
      {previous.length > 0 ? (
        <p className="mt-2 text-muted-foreground">
          Previously categorized as{' '}
          <span className="font-medium text-foreground">
            {previous.join(' › ')}
          </span>
          .
        </p>
      ) : null}
    </div>
  )
}
