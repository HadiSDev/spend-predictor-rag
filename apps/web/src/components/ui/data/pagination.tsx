import { ChevronLeft, ChevronRight, MoreHorizontal } from 'lucide-react'
import { cn } from '../cn'
import { Button } from '../actions/button'
import { IconButton } from '../actions/icon-button'

export interface PaginationProps {
  page: number
  pageCount: number
  onPageChange: (page: number) => void
  siblingCount?: number
  className?: string
}

function pageRange(
  page: number,
  pageCount: number,
  siblings: number,
): Array<number | 'ellipsis'> {
  const range: Array<number | 'ellipsis'> = []
  const first = 1
  const last = pageCount
  const start = Math.max(page - siblings, first)
  const end = Math.min(page + siblings, last)
  range.push(first)
  if (start > first + 1) {
    range.push('ellipsis')
  }
  for (let p = start; p <= end; p++) {
    if (p !== first && p !== last) {
      range.push(p)
    }
  }
  if (end < last - 1) {
    range.push('ellipsis')
  }
  if (last > first) {
    range.push(last)
  }
  return range
}

/** Controlled pagination. Renders nothing when there is a single page. */
export function Pagination({
  page,
  pageCount,
  onPageChange,
  siblingCount = 1,
  className,
}: PaginationProps) {
  if (pageCount <= 1) {
    return null
  }
  const items = pageRange(page, pageCount, siblingCount)
  return (
    <nav
      className={cn('flex items-center gap-1', className)}
      aria-label="Pagination"
    >
      <IconButton
        aria-label="Previous page"
        variant="ghost"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        <ChevronLeft />
      </IconButton>
      {items.map((item, i) =>
        item === 'ellipsis' ? (
          <span
            key={`e${i}`}
            className="grid size-10 place-items-center text-muted-foreground"
          >
            <MoreHorizontal className="size-4" />
          </span>
        ) : (
          <Button
            key={item}
            size="icon"
            variant={item === page ? 'primary' : 'ghost'}
            aria-current={item === page ? 'page' : undefined}
            onClick={() => onPageChange(item)}
          >
            {item}
          </Button>
        ),
      )}
      <IconButton
        aria-label="Next page"
        variant="ghost"
        disabled={page >= pageCount}
        onClick={() => onPageChange(page + 1)}
      >
        <ChevronRight />
      </IconButton>
    </nav>
  )
}
