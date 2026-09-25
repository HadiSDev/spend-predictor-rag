import { AlertTriangle } from 'lucide-react'
import { Badge } from '#/components/ui'
import type { InvoiceLineRead } from '#/lib/api/types'

/** Reader-facing labels for line categorization statuses. */
export const LINE_STATUS_LABEL: Record<string, string> = {
  uncategorized: 'Uncategorized',
  ai_failed: 'AI categorization failed',
  ai_categorized: 'AI categorized',
  verified: 'Verified',
}

/** Badge variant for a line status. */
export function lineStatusVariant(
  status: string,
): 'default' | 'destructive' | 'success' {
  if (status === 'verified') {
    return 'success'
  }
  if (status === 'ai_failed') {
    return 'destructive'
  }
  return 'default'
}

export interface LineStatusBadgeProps {
  line: InvoiceLineRead
}

/** A line's categorization status plus stale-category and low-confidence flags. */
export function LineStatusBadge({ line }: LineStatusBadgeProps) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge variant={lineStatusVariant(line.status)}>
        {LINE_STATUS_LABEL[line.status] ?? line.status}
      </Badge>
      {line.category_stale ? (
        <Badge variant="warning">
          <AlertTriangle className="mr-1 size-3" aria-hidden />
          Unresolved category
        </Badge>
      ) : null}
      {line.needs_review ? (
        <Badge variant="warning">Low confidence</Badge>
      ) : null}
    </span>
  )
}
