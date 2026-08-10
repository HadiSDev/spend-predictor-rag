import * as React from 'react'
import { AlertTriangle } from 'lucide-react'
import { Badge, Button, Field, FieldLabel, Progress } from '#/components/ui'
import { TreeSelector } from '#/components/spend-tree/tree-selector'
import { formatMoney, toNumber } from '#/lib/format'
import { serverErrorMessage } from '#/lib/form-errors'
import type { InvoiceLineRead, LineCorrections, SpendCategoryRead } from '#/lib/types'

/** Re-exported for existing importers (`voucher-details-tab.tsx`,
 *  `voucher-drawer.tsx`) — the canonical definition now lives in
 *  `lib/types.ts` alongside the other API-shape types, so `lib/invoices.ts`
 *  (a mutation, not a component) can use it without importing a component. */
export type { LineCorrections }

export interface LineCategoryEditorProps {
  line: InvoiceLineRead
  /** The invoice's currency — a line carries no currency of its own. */
  currency: string | null
  /** The company's spend tree, flat and shallowest-first. Null while it loads;
   *  empty when the company has no tree assigned. */
  nodes: Array<SpendCategoryRead> | null
  /** Where a manager assigns the company's tree, for the no-tree case. */
  companySettingsHref?: string
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

/** The path a line's stored levels describe, trailing levels dropped. */
function storedPath(line: InvoiceLineRead): Array<string> {
  return [line.level_1, line.level_2, line.level_3, line.level_4].filter(
    (value): value is string => value !== null && value !== '',
  )
}

/**
 * One line's categorization, correctable. The result is AI-produced, so —
 * unlike the ERP-posted amount and description beside it — it is editable:
 * provenance decides affordance.
 *
 * The category is chosen from the company's tree, never typed. A typed level
 * that matches no node produces a categorization resolving to nothing, which is
 * the silent failure the stored `spend_category_id` exists to prevent — so the
 * save sends a node id and the server derives the levels from its path.
 */
export function LineCategoryEditor({
  line,
  currency,
  nodes,
  companySettingsHref,
  onVerify,
}: LineCategoryEditorProps) {
  // Recomputed from the line every render, so a fresh server value (after a
  // save) is picked up without a synchronizing effect — only `chosen` below is
  // state the user's own action owns.
  const [chosen, setChosen] = React.useState<SpendCategoryRead | null>(null)
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const selectedId = chosen?.id ?? line.spend_category_id
  const dirty = chosen !== null && chosen.id !== line.spend_category_id

  function handleCancel() {
    setChosen(null)
    setError(null)
  }

  async function handleAccept() {
    // Only the node — the server takes the levels from its path, so a
    // correction cannot store a category that resolves to nothing.
    const corrections: LineCorrections = dirty ? { spend_category_id: chosen!.id } : {}

    setSubmitting(true)
    setError(null)
    try {
      await onVerify(line.id, corrections)
      setChosen(null)
    } catch (failure) {
      setError(serverErrorMessage(failure))
    } finally {
      setSubmitting(false)
    }
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
          {stale ? (
            // Distinct from `ai_failed` in words as well as colour: nothing
            // failed here, the taxonomy moved out from under a decision.
            <Badge variant="warning">
              <AlertTriangle className="mr-1 size-3" aria-hidden />
              Needs review
            </Badge>
          ) : null}
          <Badge variant={statusVariant(line.status)}>
            {STATUS_LABEL[line.status] ?? line.status}
          </Badge>
        </div>
      </div>

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

      <div className="flex items-center gap-2">
        <Button size="sm" disabled={submitting} onClick={() => void handleAccept()}>
          {submitting ? 'Accepting…' : dirty ? 'Save & verify' : 'Accept'}
        </Button>
        <Button size="sm" variant="ghost" disabled={submitting || !dirty} onClick={handleCancel}>
          Cancel
        </Button>
      </div>
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
