import * as React from 'react'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
} from '#/components/ui'
import { serverErrorMessage } from '#/lib/form-errors'

export interface DangerZoneProps {
  organizationName: string
  /** Whether the caller may suspend the organization. */
  canManage: boolean
  onSuspend: () => Promise<unknown>
}

/** Organization suspension, hidden from callers who may not manage it. */
export function DangerZone({
  organizationName,
  canManage,
  onSuspend,
}: DangerZoneProps) {
  const [open, setOpen] = React.useState(false)
  const [confirmation, setConfirmation] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const matches = confirmation.trim() === organizationName

  if (!canManage) {
    return null
  }

  async function handleSuspend() {
    setBusy(true)
    setError(null)
    try {
      await onSuspend()
      setOpen(false)
    } catch (failure) {
      setError(serverErrorMessage(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <CardTitle className="text-destructive">Danger zone</CardTitle>
        <CardDescription>
          Suspending retains all of this organization’s data, but blocks access
          for everyone until it is restored. The suspension also applies in
          Clerk.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button variant="destructive" onClick={() => setOpen(true)}>
          Suspend organization
        </Button>

        <AlertDialog
          open={open}
          onOpenChange={(next: boolean) => {
            setOpen(next)
            if (!next) {
              setConfirmation('')
              setError(null)
            }
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Suspend {organizationName}?</AlertDialogTitle>
              <AlertDialogDescription>
                Everyone loses access immediately. No data is deleted, and an
                administrator can restore the organization later.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="flex flex-col gap-2">
              <label
                htmlFor="suspend-confirmation"
                className="text-sm text-muted-foreground"
              >
                Type{' '}
                <span className="font-medium text-foreground">
                  {organizationName}
                </span>{' '}
                to confirm.
              </label>
              <Input
                id="suspend-confirmation"
                value={confirmation}
                autoComplete="off"
                onChange={(event) => setConfirmation(event.target.value)}
              />
              {error ? (
                <p className="text-sm text-destructive">{error}</p>
              ) : null}
            </div>
            <AlertDialogFooter>
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                disabled={!matches || busy}
                onClick={handleSuspend}
              >
                {busy ? 'Suspending…' : 'Suspend organization'}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  )
}
