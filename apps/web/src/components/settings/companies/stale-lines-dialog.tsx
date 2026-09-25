import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
} from '#/components/ui'
import type { CompanyRead } from '#/lib/api/types'

export interface StaleLinesState {
  company: CompanyRead
  staleLines: number
}

export interface StaleLinesDialogProps {
  state: StaleLinesState | null
  onClose: () => void
  onReview?: (companyId: string) => void
}

export function StaleLinesDialog({
  state,
  onClose,
  onReview,
}: StaleLinesDialogProps) {
  return (
    <AlertDialog
      open={state !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose()
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {state?.staleLines} line
            {state?.staleLines === 1 ? '' : 's'} need reviewing
          </AlertDialogTitle>
          <AlertDialogDescription>
            {state?.company.name}&rsquo;s spend tree changed. Those lines keep
            the categories they were given — nothing was deleted — but those
            categories are not in the new tree, so someone should re-decide
            them.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Later
          </Button>
          {onReview && state ? (
            <Button
              onClick={() => {
                onReview(state.company.id)
                onClose()
              }}
            >
              Review them
            </Button>
          ) : null}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
