import { BarChart3 } from 'lucide-react'
import { cn } from './cn'

export interface LoadingScreenProps {
  /** Optional status line under the mark (e.g. "Preparing your workspace…"). */
  message?: string
  className?: string
}

// Staggered so the bars ripple left→right like a chart drawing itself.
const BAR_DELAYS = ['0ms', '120ms', '240ms', '360ms']

/**
 * Full-screen, on-brand loading state. Layered for depth (atmospheric glow
 * behind a pulsing brand mark) with an animated "spend bars" indicator that
 * echoes the logo. Motion is GPU-safe (transform/opacity) and pauses under
 * `prefers-reduced-motion`.
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
      {/* depth-1 — atmospheric glow */}
      <div
        aria-hidden="true"
        className="ep-loading-glow pointer-events-none absolute size-[36rem] rounded-full bg-primary/25 blur-3xl"
      />

      <div className="relative flex flex-col items-center gap-7">
        {/* depth-3 — brand mark + wordmark */}
        <div className="flex items-center gap-2.5">
          <div className="ep-loading-mark grid size-10 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-card">
            <BarChart3 className="size-5" />
          </div>
          <span className="font-display text-xl font-semibold tracking-tight">Spend Predictor</span>
        </div>

        {/* depth-4 — animated spend bars */}
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
