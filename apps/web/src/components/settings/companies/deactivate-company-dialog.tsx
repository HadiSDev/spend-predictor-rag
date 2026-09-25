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

export interface DeactivateCompanyDialogProps {
  company: CompanyRead | undefined
  busy: boolean
  error: string | null
  onCancel: () => void
  onDismiss: () => void
  onConfirm: (company: CompanyRead) => void
}

export function DeactivateCompanyDialog({
  company,
  busy,
  error,
  onCancel,
  onDismiss,
  onConfirm,
}: DeactivateCompanyDialogProps) {
  return (
    <AlertDialog
      open={company !== undefined}
      onOpenChange={(next: boolean) => {
        if (!next) {
          onDismiss()
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Deactivate {company?.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            It stops appearing in the default company list and syncs nothing
            further. Its invoices and ledger entries are kept, and you can
            reactivate it at any time.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <AlertDialogFooter>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={busy}
            onClick={() => {
              if (company) {
                onConfirm(company)
              }
            }}
          >
            {busy ? 'Deactivating…' : 'Deactivate'}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
