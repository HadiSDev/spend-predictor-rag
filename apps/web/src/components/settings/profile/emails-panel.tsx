import * as React from 'react'
import { Badge, Button, CodeInput, Input } from '#/components/ui'
import type { ClerkEmailAddress, ClerkUser } from '#/lib/auth/clerk-types'
import { serverErrorMessage } from '#/lib/form-errors'
import { SettingsCard } from '#/components/settings/form'

export interface EmailRow {
  id: string
  address: string
  verified: boolean
  primary: boolean
}

export interface EmailsViewProps {
  emails: Array<EmailRow>
  /** Create the address and send its verification code. */
  onAdd: (address: string) => Promise<unknown>
  /** Verify the address created by the last `onAdd`. */
  onVerify: (code: string) => Promise<unknown>
  /** Send a fresh code for the address awaiting verification. */
  onResend: () => Promise<unknown>
  onSetPrimary: (id: string) => Promise<unknown>
  onRemove: (id: string) => Promise<unknown>
}

/** Email addresses with their two-step verification flow. */
export function EmailsView({
  emails,
  onAdd,
  onVerify,
  onResend,
  onSetPrimary,
  onRemove,
}: EmailsViewProps) {
  const [address, setAddress] = React.useState('')
  const [code, setCode] = React.useState('')
  const [pending, setPending] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  async function run(action: () => Promise<unknown>, after?: () => void) {
    setBusy(true)
    setError(null)
    try {
      await action()
      after?.()
    } catch (failure) {
      setError(serverErrorMessage(failure))
    } finally {
      setBusy(false)
    }
  }

  function handleAdd(event: React.FormEvent) {
    event.preventDefault()
    if (!address.trim()) {
      return
    }
    void run(
      () => onAdd(address.trim()),
      () => setPending(address.trim()),
    )
  }

  function submitCode(value: string) {
    if (!value.trim()) {
      return
    }
    void run(
      () => onVerify(value.trim()),
      () => {
        setPending(null)
        setAddress('')
        setCode('')
      },
    )
  }

  function handleVerify(event: React.FormEvent) {
    event.preventDefault()
    submitCode(code)
  }

  return (
    <SettingsCard
      title="Email addresses"
      description="Used to sign in and to reach you. The primary address can’t be removed."
    >
      <div className="flex flex-col gap-4">
        <ul className="flex flex-col divide-y divide-border">
          {emails.map((email) => (
            <li
              key={email.id}
              className="flex flex-wrap items-center gap-3 py-3"
            >
              <span className="min-w-0 flex-1 truncate text-sm">
                {email.address}
              </span>
              {email.primary ? <Badge variant="primary">Primary</Badge> : null}
              <Badge variant={email.verified ? 'success' : 'warning'}>
                {email.verified ? 'Verified' : 'Unverified'}
              </Badge>
              {!email.primary && email.verified ? (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => void run(() => onSetPrimary(email.id))}
                >
                  Make primary
                </Button>
              ) : null}
              {!email.primary ? (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => void run(() => onRemove(email.id))}
                >
                  Remove
                </Button>
              ) : null}
            </li>
          ))}
        </ul>

        {pending ? (
          <form className="flex flex-col gap-3" onSubmit={handleVerify}>
            <p className="text-sm text-muted-foreground">
              Enter the code sent to{' '}
              <span className="font-medium text-foreground">{pending}</span>.
            </p>
            <CodeInput
              aria-label="Verification code"
              value={code}
              onChange={setCode}
              disabled={busy}
              onComplete={(value) => {
                if (!busy) {
                  submitCode(value)
                }
              }}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" disabled={busy || !code.trim()}>
                {busy ? 'Verifying…' : 'Verify'}
              </Button>
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => void run(() => onResend())}
              >
                Resend code
              </Button>
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  setPending(null)
                  setCode('')
                  setError(null)
                }}
              >
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={handleAdd}
          >
            <Input
              aria-label="New email address"
              type="email"
              placeholder="you@company.com"
              className="max-w-72"
              value={address}
              onChange={(event) => setAddress(event.target.value)}
            />
            <Button type="submit" disabled={busy || !address.trim()}>
              {busy ? 'Adding…' : 'Add address'}
            </Button>
          </form>
        )}

        {error ? <p className="text-sm text-destructive">{error}</p> : null}
      </div>
    </SettingsCard>
  )
}

/** Binds the view to Clerk's email-address resources. */
export function EmailsPanel({ user }: { user: ClerkUser }) {
  const pending = React.useRef<ClerkEmailAddress | null>(null)

  const emails: Array<EmailRow> = user.emailAddresses.map((email) => ({
    id: email.id,
    address: email.emailAddress,
    verified: email.verification.status === 'verified',
    primary: email.id === user.primaryEmailAddressId,
  }))

  return (
    <EmailsView
      emails={emails}
      onAdd={async (address) => {
        const created = await user.createEmailAddress({ email: address })
        pending.current = created
        await created.prepareVerification({ strategy: 'email_code' })
      }}
      onVerify={async (code) => {
        if (!pending.current) {
          throw new Error('No address is awaiting verification.')
        }
        await pending.current.attemptVerification({ code })
        pending.current = null
        await user.reload()
      }}
      onResend={async () => {
        if (!pending.current) {
          throw new Error('No address is awaiting verification.')
        }
        await pending.current.prepareVerification({ strategy: 'email_code' })
      }}
      onSetPrimary={async (id) => {
        await user.update({ primaryEmailAddressId: id })
      }}
      onRemove={async (id) => {
        await user.emailAddresses.find((email) => email.id === id)?.destroy()
        await user.reload()
      }}
    />
  )
}
