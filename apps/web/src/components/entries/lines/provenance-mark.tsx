import { Tooltip, TooltipContent, TooltipTrigger } from '#/components/ui'
import type { LineOrigin } from '#/lib/api/types'

/** Marks for line origins a reader would not otherwise expect. */
const PROVENANCE_MARKS: Partial<
  Record<LineOrigin, { label: string; explanation: string }>
> = {
  entry_fallback: {
    label: 'from posting',
    explanation:
      'Stands in for a ledger posting — no document was read for this voucher, ' +
      'so this is the bookkeeper’s description rather than what was bought.',
  },
  human: {
    label: 'added by hand',
    explanation:
      'Written by a reviewer rather than read from the ERP or the document. ' +
      'A sync will not change or remove it.',
  },
}

export function ProvenanceMark({ origin }: { origin: LineOrigin }) {
  const mark = PROVENANCE_MARKS[origin]
  if (mark === undefined) {
    return null
  }
  const { label, explanation } = mark
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            tabIndex={0}
            aria-label={explanation}
            className="cursor-help rounded border border-border px-1 text-[10px] leading-4 text-muted-foreground"
          />
        }
      >
        {label}
      </TooltipTrigger>
      <TooltipContent>{explanation}</TooltipContent>
    </Tooltip>
  )
}
