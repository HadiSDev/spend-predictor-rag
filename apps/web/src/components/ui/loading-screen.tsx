import { Logo } from '#/components/brand/logo'
import { cn } from './cn'

export interface LoadingScreenProps {
  /** Optional status line under the mark (e.g. "Preparing your workspace…"). */
  message?: string
  className?: string
}

// Staggered so the bars ripple left→right like a chart drawing itself.
const BAR_DELAYS = ['0ms', '120ms', '240ms', '360ms']

/**
 * Full-screen, on-brand loading state: the Steelyard lockup, still, above an
 * animated "spend bars" indicator. The logo itself never moves, glows or pulses
 * — the pack forbids effects on the mark — so the motion lives in the bars.
 * GPU-safe (transform/opacity) and paused under `prefers-reduced-motion`.
 */
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

        {/* animated spend bars */}
        <div className="flex h-9 items-end gap-1.5" aria-hidden="true">
          {BAR_DELAYS.map((delay) => (
            <span
              key={delay}
              className="ep-loading-bar h-full w-1.5 rounded-full bg-foreground/80"
              style={{ animationDelay: delay }}
            />
          ))}
        </div>

        {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
        <span className="sr-only">Loading{message ? `: ${message}` : ''}</span>
      </div>
    </div>
  )
}
