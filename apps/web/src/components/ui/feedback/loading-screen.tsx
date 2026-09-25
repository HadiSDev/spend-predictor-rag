import { Logo } from '#/components/brand/logo'
import { cn } from '../cn'

export interface LoadingScreenProps {
  /** Optional status line under the mark (e.g. "Preparing your workspace…"). */
  message?: string
  className?: string
}

const BAR_DELAYS = ['0ms', '120ms', '240ms', '360ms']

/** Full-screen loading state: the Steelyard lockup above animated spend bars. */
export function LoadingScreen({ message, className }: LoadingScreenProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'relative grid min-h-screen place-items-center overflow-hidden bg-background',
        className,
      )}
    >
      <div className="relative flex flex-col items-center gap-7">
        <Logo width={160} />

        <div className="flex h-9 items-end gap-1.5" aria-hidden="true">
          {BAR_DELAYS.map((delay) => (
            <span
              key={delay}
              className="ep-loading-bar h-full w-1.5 rounded-full bg-foreground/80"
              style={{ animationDelay: delay }}
            />
          ))}
        </div>

        {message ? (
          <p className="text-sm text-muted-foreground">{message}</p>
        ) : null}
        <span className="sr-only">Loading{message ? `: ${message}` : ''}</span>
      </div>
    </div>
  )
}
