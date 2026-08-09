import * as React from 'react'
import { Badge, Button, Field, FieldControl, FieldLabel, Progress } from '#/components/ui'
import { formatMoney, toNumber } from '#/lib/format'
import { serverErrorMessage } from '#/lib/form-errors'
import type { InvoiceLineRead } from '#/lib/types'

/** Fields `POST /invoice-lines/{id}/verify` accepts as corrections. Only the
 *  levels are editable here — everything else on the line is either evidence
 *  (amount, description) or derived server-side (account_code/name). */
export type LineCorrections = Partial<Record<'level_1' | 'level_2' | 'level_3', string>>

export interface LineCategoryEditorProps {
  line: InvoiceLineRead
  /** The invoice's currency — a line carries no currency of its own. */
  currency: string | null
  /** Sending an empty object accepts the AI result as-is (`verify`, not `edit`). */
  onVerify: (lineId: string, corrections: LineCorrections) => Promise<void>
}

const STATUS_LABEL: Record<string, string> = {
  uncategorized: 'Uncategorized',
  ai_failed: 'AI categorization failed',
  ai_categorized: 'AI categorized',
  verified: 'Verified',
}

function statusVariant(status: string): 'default' | 'destructive' | 'success' {
  if (status === 'verified') return 'success'
  if (status === 'ai_failed') return 'destructive'
  return 'default'
}

interface LevelValues {
  level_1: string
  level_2: string
  level_3: string
}

function levelsFromLine(line: InvoiceLineRead): LevelValues {
  return {
    level_1: line.level_1 ?? '',
    level_2: line.level_2 ?? '',
    level_3: line.level_3 ?? '',
  }
}

/**
 * One line's categorization, correctable. The result is AI-produced, so —
 * unlike the ERP-posted amount and description beside it — it renders as real
 * inputs: provenance decides affordance.
 */
export function LineCategoryEditor({ line, currency, onVerify }: LineCategoryEditorProps) {
  // Recomputed from the line every render, so a fresh server value (after a
  // save) is picked up without a synchronizing effect — only `values` below
  // is state a user's keystrokes actually own.
  const original = levelsFromLine(line)
  const [values, setValues] = React.useState<LevelValues>(original)
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const dirty =
    values.level_1 !== original.level_1 ||
    values.level_2 !== original.level_2 ||
    values.level_3 !== original.level_3

  function handleCancel() {
    setValues(original)
    setError(null)
  }

  async function handleAccept() {
    const corrections: LineCorrections = {}
    if (values.level_1 !== original.level_1) corrections.level_1 = values.level_1
    if (values.level_2 !== original.level_2) corrections.level_2 = values.level_2
    if (values.level_3 !== original.level_3) corrections.level_3 = values.level_3

    setSubmitting(true)
    setError(null)
    try {
      await onVerify(line.id, corrections)
    } catch (failure) {
      setError(serverErrorMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  const confidencePct =
    line.confidence === null ? null : Math.round(toNumber(line.confidence) * 100)

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
        <Badge variant={statusVariant(line.status)}>{STATUS_LABEL[line.status] ?? line.status}</Badge>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field>
          <FieldLabel>Level 1</FieldLabel>
          <FieldControl
            value={values.level_1}
            onChange={(event) =>
              setValues((current) => ({ ...current, level_1: event.target.value }))
            }
          />
        </Field>
        <Field>
          <FieldLabel>Level 2</FieldLabel>
          <FieldControl
            value={values.level_2}
            onChange={(event) =>
              setValues((current) => ({ ...current, level_2: event.target.value }))
            }
          />
        </Field>
        <Field>
          <FieldLabel>Level 3</FieldLabel>
          <FieldControl
            value={values.level_3}
            onChange={(event) =>
              setValues((current) => ({ ...current, level_3: event.target.value }))
            }
          />
        </Field>
      </div>

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

      <div className="flex items-center gap-2">
        <Button size="sm" disabled={submitting} onClick={() => void handleAccept()}>
          {submitting ? 'Accepting…' : 'Accept'}
        </Button>
        <Button size="sm" variant="ghost" disabled={submitting || !dirty} onClick={handleCancel}>
          Cancel
        </Button>
      </div>
    </div>
  )
}
