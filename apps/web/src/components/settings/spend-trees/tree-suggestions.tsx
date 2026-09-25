import * as React from 'react'
import { ChevronDown, Lightbulb } from 'lucide-react'
import { Badge, Button, Card, IconButton } from '#/components/ui'
import { cn } from '#/components/ui/cn'
import { formatMoney } from '#/lib/format/format'
import type { SpendCategorySuggestionRead } from '#/lib/api/types'

export interface TreeSuggestionsProps {
  suggestions: Array<SpendCategorySuggestionRead>
  canManage: boolean
  onAccept: (id: string) => Promise<unknown>
  onDismiss: (id: string) => Promise<unknown>
  /** Puts a dismissal back. */
  onReopen: (id: string) => Promise<unknown>
  /** Opens the line that argued for a proposal. */
  onOpenLine?: (line: { id: string; invoiceId: string | null }) => void
}

/** The categories this tree is missing, proposed from the company's own spend. */
export function TreeSuggestions({
  suggestions,
  canManage,
  onAccept,
  onDismiss,
  onReopen,
  onOpenLine,
}: TreeSuggestionsProps) {
  const [open, setOpen] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState<string | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [undo, setUndo] = React.useState<SpendCategorySuggestionRead | null>(
    null,
  )

  const pending = suggestions.filter((s) => s.state === 'pending')
  if (pending.length === 0 && !undo) {
    return null
  }

  async function run(id: string, action: (id: string) => Promise<unknown>) {
    setBusy(id)
    setError(null)
    try {
      await action(id)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'That did not work.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card className="border-warning/40 bg-warning/5 p-4">
      <div className="flex items-center gap-2">
        <Lightbulb className="size-4 text-warning" aria-hidden />
        <h3 className="font-display text-sm font-medium">
          {pending.length === 1
            ? '1 category this tree may be missing'
            : `${pending.length} categories this tree may be missing`}
        </h3>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Suggested from spend the categorizer had no confident home for. Nothing
        is added until you accept it.
      </p>

      {error ? (
        <p role="alert" className="mt-2 text-xs text-destructive">
          {error}
        </p>
      ) : null}

      <ul className="mt-3 flex flex-col gap-2">
        {pending.map((suggestion) => {
          const expanded = open === suggestion.id
          return (
            <li
              key={suggestion.id}
              className="rounded-md border border-border bg-background"
            >
              <div className="flex flex-wrap items-start gap-2 p-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{suggestion.name}</span>
                    {suggestion.parent_path ? (
                      <Badge variant="default">
                        under {suggestion.parent_path}
                      </Badge>
                    ) : (
                      <Badge variant="warning">
                        its parent no longer exists
                      </Badge>
                    )}
                  </div>
                  {suggestion.description ? (
                    <p className="mt-0.5 text-sm text-muted-foreground">
                      {suggestion.description}
                    </p>
                  ) : null}
                  {suggestion.rationale ? (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {suggestion.rationale}
                    </p>
                  ) : null}
                </div>

                {canManage ? (
                  <div className="flex items-center gap-1.5">
                    <Button
                      size="sm"
                      disabled={
                        !suggestion.acceptable || busy === suggestion.id
                      }
                      onClick={() => void run(suggestion.id, onAccept)}
                    >
                      Add to tree
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy === suggestion.id}
                      onClick={() => {
                        setUndo(suggestion)
                        void run(suggestion.id, onDismiss)
                      }}
                    >
                      Dismiss
                    </Button>
                  </div>
                ) : null}

                <IconButton
                  aria-label={expanded ? 'Hide the lines' : 'Show the lines'}
                  onClick={() => setOpen(expanded ? null : suggestion.id)}
                >
                  <ChevronDown
                    className={cn(
                      'size-4 transition-transform',
                      expanded && 'rotate-180',
                    )}
                    aria-hidden
                  />
                </IconButton>
              </div>

              {expanded ? (
                <div className="border-t border-border px-3 py-2">
                  <p className="text-xs text-muted-foreground">
                    {suggestion.evidence_count === 1
                      ? '1 line argued for this'
                      : `${suggestion.evidence_count} lines argued for this`}
                  </p>
                  <ul className="mt-1.5 flex flex-col gap-1">
                    {suggestion.evidence.map((line) => (
                      <li
                        key={line.id}
                        className="flex flex-wrap items-baseline gap-2 text-sm"
                      >
                        <button
                          type="button"
                          className="text-left underline-offset-2 hover:underline"
                          onClick={() =>
                            onOpenLine?.({
                              id: line.id,
                              invoiceId: line.invoice_id,
                            })
                          }
                        >
                          {line.item_name ??
                            line.description ??
                            'Untitled line'}
                        </button>
                        {line.vendor_name ? (
                          <span className="text-xs text-muted-foreground">
                            {line.vendor_name}
                          </span>
                        ) : null}
                        {line.amount === null ? null : (
                          <span className="text-xs tabular-nums text-muted-foreground">
                            {formatMoney(line.amount, line.currency)}
                          </span>
                        )}
                        {line.level_3 || line.level_2 ? (
                          <span className="text-xs text-muted-foreground">
                            filed under {line.level_3 ?? line.level_2}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </li>
          )
        })}
      </ul>

      {undo ? (
        <div className="mt-3 flex items-center justify-between gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm">
          <span>Dismissed “{undo.name}”.</span>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy === undo.id}
            onClick={() => {
              const target = undo.id
              setUndo(null)
              void run(target, onReopen)
            }}
          >
            Undo
          </Button>
        </div>
      ) : null}
    </Card>
  )
}
