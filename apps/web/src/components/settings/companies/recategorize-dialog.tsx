import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
} from '#/components/ui'
import type { CompanyRead, RecategorizeResult } from '#/lib/api/types'

export interface RecategorizeState {
  company: CompanyRead
  result: RecategorizeResult | null
  busy: boolean
}

/** Confirms putting a company's failed lines back in the categorizer's queue. */
export function RecategorizeDialog({
  state,
  onClose,
  onRun,
}: {
  state: RecategorizeState | null
  onClose: () => void
  onRun: () => void | Promise<void>
}) {
  const result = state?.result

  return (
    <AlertDialog
      open={state !== null}
      onOpenChange={(next: boolean) => {
        if (!next && !state?.busy) {
          onClose()
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {result
              ? result.queued === 0
                ? 'Nothing to queue'
                : 'Queued for the categorizer'
              : `Recategorize ${state?.company.name}’s failed lines?`}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {result ? (
              result.queued === 0 ? (
                <>
                  No failed lines were found, so nothing changed. Only lines the
                  AI tried and failed on are eligible.
                </>
              ) : (
                <>
                  {result.queued} lines are queued. They will be categorized on
                  the next sync run — nothing has been categorized yet.
                </>
              )
            ) : (
              <>
                Lines the AI failed on are returned to the queue and categorized
                on the next sync run. Nothing is categorized right now, and
                lines a person has verified are left alone.
              </>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          {result ? (
            <Button onClick={onClose}>Done</Button>
          ) : (
            <>
              <Button variant="ghost" onClick={onClose} disabled={state?.busy}>
                Not now
              </Button>
              <Button onClick={() => void onRun()} disabled={state?.busy}>
                {state?.busy ? 'Queueing…' : 'Queue for recategorization'}
              </Button>
            </>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
