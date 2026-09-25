import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
} from '#/components/ui'
import type { CompanyRead, FxRecomputeResult } from '#/lib/api/types'

export interface RecomputeState {
  company: CompanyRead
  /** Set when the prompt follows a currency change; null when opened directly. */
  currency: string | null
  result: FxRecomputeResult | null
  busy: boolean
}

/** Offers to rewrite a company's stored figures into its reporting currency. */
export function RecomputeDialog({
  state,
  onClose,
  onRun,
}: {
  state: RecomputeState | null
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
              ? 'Figures recomputed'
              : `Recompute ${state?.company.name}’s figures?`}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {result ? (
              <>
                {result.converted} converted, {result.unchanged} already
                current, and {result.unconverted} left unconverted — no rate was
                available for those.
              </>
            ) : state?.currency ? (
              <>
                Everything already imported is still stored in the previous
                currency. Recompute to restate it in {state.currency}, each
                amount at the exchange rate from its own transaction date.
              </>
            ) : (
              <>
                Restates every imported amount in {state?.company.base_currency}
                , each at the exchange rate from its own transaction date.
                Amounts already converted are left untouched.
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
                {state?.busy ? 'Recomputing…' : 'Recompute'}
              </Button>
            </>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
