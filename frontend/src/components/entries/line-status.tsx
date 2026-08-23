import { AlertTriangle } from 'lucide-react'
import { Badge } from '#/components/ui'
import type { InvoiceLineRead } from '#/lib/types'

/**
 * A line's categorization status, in the reader's terms.
 *
 * The Spend category column cannot carry this: an empty category means "nobody
 * has categorized this yet", "the AI tried and failed", and "this company has
 * no spend tree" identically, and only the middle one is a problem.
 */
export const LINE_STATUS_LABEL: Record<string, string> = {
  uncategorized: 'Uncategorized',
  ai_failed: 'AI categorization failed',
  ai_categorized: 'AI categorized',
  verified: 'Verified',
}

/**
 * Only `ai_failed` is a problem state.
 *
 * `uncategorized` is a backlog and `verified` is the goal, so tinting either as
 * an error would flag most of the ledger — the same reasoning that keeps the
 * provenance mark off ordinary lines.
 *
 * It stayed `destructive` when the model stopped being allowed to decline, and
 * that is the point of the change: `ai_failed` now only ever means the model
 * answered with a category we never offered, which really is a fault. It used to
 * also mean "the model looked and nothing fitted", which is not one, and dressing
 * that in red told a reviewer the software was broken when the taxonomy was
 * merely incomplete.
 */
export function lineStatusVariant(
  status: string,
): 'default' | 'destructive' | 'success' {
  if (status === 'verified') return 'success'
  if (status === 'ai_failed') return 'destructive'
  return 'default'
}

export interface LineStatusBadgeProps {
  line: InvoiceLineRead
}

/**
 * Where a line stands in the categorization lifecycle, plus whether its
 * category still resolves.
 *
 * `category_stale` is rendered *beside* the status, never instead of it. It is
 * computed rather than stored and is orthogonal to the lifecycle — a line can
 * be `verified` and stale at once, meaning a human categorized it and the
 * taxonomy later moved out from under the decision. Collapsing the two into one
 * badge would erase whichever real status the line holds.
 *
 * The status comes from the payload's `status`, never from whether the levels
 * are populated: an `ai_failed` line and an `uncategorized` line both have none.
 */
export function LineStatusBadge({ line }: LineStatusBadgeProps) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge variant={lineStatusVariant(line.status)}>
        {LINE_STATUS_LABEL[line.status] ?? line.status}
      </Badge>
      {line.category_stale ? (
        // Distinct from `ai_failed` in words as well as colour: nothing failed
        // here, the taxonomy moved.
        <Badge variant="warning">
          <AlertTriangle className="mr-1 size-3" aria-hidden />
          Unresolved category
        </Badge>
      ) : null}
      {line.needs_review ? (
        // Named for its cause, not for the work it implies. "Needs review" would
        // be true of a stale line too, and a reviewer seeing the same words on
        // two different problems learns nothing from either.
        <Badge variant="warning">Low confidence</Badge>
      ) : null}
    </span>
  )
}
