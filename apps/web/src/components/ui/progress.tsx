import * as React from 'react'
import { Progress as BaseProgress } from '@base-ui-components/react/progress'
import { cn } from './cn'

export interface ProgressProps extends React.ComponentProps<typeof BaseProgress.Root> {
  /** Show the built-in percentage label above the track. */
  showValue?: boolean
  label?: React.ReactNode
}

export const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className, showValue, label, ...props }, ref) => (
    <BaseProgress.Root ref={ref} className={cn('flex flex-col gap-1.5', className)} {...props}>
      {(label != null || showValue) && (
        <div className="flex items-center justify-between text-sm">
          {label != null && <BaseProgress.Label className="text-foreground">{label}</BaseProgress.Label>}
          {showValue && <BaseProgress.Value className="text-muted-foreground tabular-nums" />}
        </div>
      )}
      <BaseProgress.Track className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <BaseProgress.Indicator className="h-full rounded-full bg-primary transition-all duration-300" />
      </BaseProgress.Track>
    </BaseProgress.Root>
  ),
)
Progress.displayName = 'Progress'
