import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Input,
} from '#/components/ui'
import type { CompanyDeleteBlocked, CompanyRead } from '#/lib/api/types'

/** State of the delete-company dialog; `counts` stays null until the server refuses once. */
export interface DeleteCompanyState {
  company: CompanyRead
  counts: CompanyDeleteBlocked | null
  typed: string
}

export interface DeleteCompanyDialogProps {
  state: DeleteCompanyState | null
  busy: boolean
  error: string | null
  onTypedChange: (typed: string) => void
  onCancel: () => void
  onDismiss: () => void
  onConfirm: () => void
}

export function DeleteCompanyDialog({
  state,
  busy,
  error,
  onTypedChange,
  onCancel,
  onDismiss,
  onConfirm,
}: DeleteCompanyDialogProps) {
  return (
    <AlertDialog
      open={state !== null}
      onOpenChange={(next: boolean) => {
        if (!next && !busy) {
          onDismiss()
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {state?.company.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            {state?.counts ? (
              <>
                This destroys {state.counts.invoices} invoice
                {state.counts.invoices === 1 ? '' : 's'}, {state.counts.lines}{' '}
                line
                {state.counts.lines === 1 ? '' : 's'} and {state.counts.entries}{' '}
                posting
                {state.counts.entries === 1 ? '' : 's'}
                {state.counts.earliest && state.counts.latest ? (
                  <>
                    {' '}
                    covering {state.counts.earliest} to {state.counts.latest}
                  </>
                ) : null}
                . This cannot be undone.
              </>
            ) : (
              <>
                This destroys the company and everything it owns — invoices,
                lines and ledger postings. This cannot be undone.
              </>
            )}{' '}
            Deactivate it instead to retire it while keeping the records.
            Suppliers are shared across the platform and are kept either way.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm" htmlFor="confirm-company-name">
            Type{' '}
            <span className="font-medium text-foreground">
              {state?.company.name}
            </span>{' '}
            to confirm
          </label>
          <Input
            id="confirm-company-name"
            aria-label="Confirm the company name"
            autoComplete="off"
            value={state?.typed ?? ''}
            onChange={(event) => onTypedChange(event.target.value)}
          />
        </div>

        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        <AlertDialogFooter>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={busy || state?.typed.trim() !== state?.company.name}
            onClick={onConfirm}
          >
            {busy ? 'Deleting…' : 'Delete permanently'}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
