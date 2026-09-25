import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
} from '#/components/ui'
import type { ReplaceBlocked } from '#/lib/api/types'

export interface ErpSwitchValues {
  erp_type: string
  label: string
  credentials: Record<string, string>
}

export interface ErpSwitchBlockedState {
  integrationId: string
  values: ErpSwitchValues
  counts: ReplaceBlocked
}

export interface ErpSwitchDialogProps {
  state: ErpSwitchBlockedState | null
  busy: boolean
  error: string | null
  onClose: () => void
  onConfirm: () => void
}

export function ErpSwitchDialog({
  state,
  busy,
  error,
  onClose,
  onConfirm,
}: ErpSwitchDialogProps) {
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
          <AlertDialogTitle>Switch ERP anyway?</AlertDialogTitle>
          <AlertDialogDescription>
            The current connection has posted {state?.counts.entries} entries
            across {state?.counts.invoices} invoices
            {state?.counts.earliest && state.counts.latest
              ? `, from ${state.counts.earliest} to ${state.counts.latest}`
              : ''}
            . None of it is deleted — but the new system will deliver those
            periods again as separate rows, so spend covering them will be
            counted twice in reports.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <AlertDialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={busy}>
            {busy ? 'Switching…' : 'Switch anyway'}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
