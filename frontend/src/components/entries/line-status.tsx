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
          Needs review
        </Badge>
      ) : null}
    </span>
  )
}
