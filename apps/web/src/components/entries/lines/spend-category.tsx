import { cn } from '#/components/ui'
import type { InvoiceLineRead } from '#/lib/api/types'

/** A line's spend category as its full path. */
export function SpendCategory({ line }: { line: InvoiceLineRead }) {
  const path = [line.level_1, line.level_2, line.level_3].filter(
    (level): level is string => Boolean(level),
  )

  if (path.length === 0) {
    return <span className="text-muted-foreground">—</span>
  }
  return (
    <span className="text-muted-foreground">
      {path.map((level, i) => (
        <span key={level}>
          {i > 0 ? <span className="mx-1 opacity-50">›</span> : null}
          <span className={cn(i === path.length - 1 && 'text-foreground')}>
            {level}
          </span>
        </span>
      ))}
    </span>
  )
}
