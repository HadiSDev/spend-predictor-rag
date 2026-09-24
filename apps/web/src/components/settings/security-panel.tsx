import * as React from 'react'
import { useForm } from 'react-hook-form'
import { useSession } from '@clerk/tanstack-react-start'
import {
  Badge,
  Button,
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
} from '#/components/ui'
import type { ClerkUser } from '#/lib/clerk-types'
import { serverErrorMessage } from '#/lib/form-errors'
import { SettingsCard, SubmitRow, useSettingsSubmit } from './form'

export interface PasswordValues {
  currentPassword: string
  newPassword: string
  confirmPassword: string
}

export interface SessionRow {
  id: string
  device: string
  lastActive: string
}

export interface ConnectionRow {
  id: string
  /** Clerk provider slug, e.g. `google`. */
  provider: string
  label: string
}

/** Providers offered for connecting. The instance may enable only some of
 * these; Clerk rejects an unsupported one and its message is surfaced. */
const PROVIDERS = [
  { strategy: 'oauth_google', provider: 'google', label: 'Google' },
  { strategy: 'oauth_microsoft', provider: 'microsoft', label: 'Microsoft' },
  { strategy: 'oauth_github', provider: 'github', label: 'GitHub' },
] as const

export interface SecurityViewProps {
  /** Whether a password already exists — decides "change" vs "set". */
  hasPassword: boolean
  onSavePassword: (values: PasswordValues) => Promise<unknown>
  sessions: Array<SessionRow>
  sessionsLoading?: boolean
  onRevokeSession: (id: string) => Promise<unknown>
  connections: Array<ConnectionRow>
  onConnect: (strategy: string) => Promise<unknown>
  onDisconnect: (id: string) => Promise<unknown>
}

export function SecurityView({
  hasPassword,
  onSavePassword,
  sessions,
  sessionsLoading = false,
  onRevokeSession,
  connections,
  onConnect,
  onDisconnect,
}: SecurityViewProps) {
  const form = useForm<PasswordValues>({
    defaultValues: { currentPassword: '', newPassword: '', confirmPassword: '' },
  })
  const submit = useSettingsSubmit()
  const [revoked, setRevoked] = React.useState<Array<string>>([])
  const [sessionError, setSessionError] = React.useState<string | null>(null)
  const [connectionError, setConnectionError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)

  // Disconnecting the last one would leave the account with no way to sign in.
  const canDisconnect = hasPassword || connections.length > 1
  const visibleSessions = sessions.filter((session) => !revoked.includes(session.id))
  const connected = new Set(connections.map((connection) => connection.provider))

  async function handleRevoke(id: string) {
    setBusy(true)
    setSessionError(null)
    try {
      await onRevokeSession(id)
      setRevoked((previous) => [...previous, id])
    } catch (error) {
      setSessionError(serverErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  async function handleConnection(action: () => Promise<unknown>) {
    setBusy(true)
    setConnectionError(null)
    try {
      await action()
    } catch (error) {
      setConnectionError(serverErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <SettingsCard
        title={hasPassword ? 'Change password' : 'Set a password'}
        description={
          hasPassword
            ? 'You’ll stay signed in on this device.'
            : 'Add a password so you can sign in without an connected account.'
        }
      >
        <Form {...form}>
          <form
            className="flex max-w-md flex-col gap-4"
            onSubmit={submit({
              form,
              run: onSavePassword,
              success: hasPassword ? 'Password changed' : 'Password set',
              resetTo: () => ({ currentPassword: '', newPassword: '', confirmPassword: '' }),
            })}
          >
            {hasPassword ? (
              <FormField
                control={form.control}
                name="currentPassword"
                rules={{ required: 'Enter your current password.' }}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Current password</FormLabel>
                    <FormControl>
                      <Input type="password" autoComplete="current-password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            ) : null}
            <FormField
              control={form.control}
              name="newPassword"
              rules={{
                required: 'Enter a new password.',
                minLength: { value: 8, message: 'Use at least 8 characters.' },
              }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>New password</FormLabel>
                  <FormControl>
                    <Input type="password" autoComplete="new-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="confirmPassword"
              rules={{
                validate: (value, values) =>
                  value === values.newPassword || 'The passwords don’t match.',
              }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Confirm new password</FormLabel>
                  <FormControl>
                    <Input type="password" autoComplete="new-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <SubmitRow form={form} label={hasPassword ? 'Change password' : 'Set password'} />
          </form>
        </Form>
      </SettingsCard>

      <SettingsCard
        title="Active sessions"
        description="Other devices signed in to your account. This device isn’t listed."
      >
        {sessionsLoading ? (
          <p className="text-sm text-muted-foreground">Loading sessions…</p>
        ) : visibleSessions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No other devices are signed in.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {visibleSessions.map((session) => (
              <li key={session.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm">{session.device}</div>
                  <div className="text-xs text-muted-foreground">{session.lastActive}</div>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => void handleRevoke(session.id)}
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        )}
        {sessionError ? <p className="mt-3 text-sm text-destructive">{sessionError}</p> : null}
      </SettingsCard>

      <SettingsCard
        title="Connected accounts"
        description="Sign in with an external provider."
      >
        <div className="flex flex-col gap-4">
          {connections.length > 0 ? (
            <ul className="flex flex-col divide-y divide-border">
              {connections.map((connection) => (
                <li key={connection.id} className="flex flex-wrap items-center gap-3 py-3">
                  <span className="min-w-0 flex-1 truncate text-sm">{connection.label}</span>
                  <Badge variant="outline">{connection.provider}</Badge>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy || !canDisconnect}
                    onClick={() => void handleConnection(() => onDisconnect(connection.id))}
                  >
                    Disconnect
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No connected accounts.</p>
          )}

          {!canDisconnect ? (
            <p className="text-sm text-muted-foreground">
              This is your only way to sign in. Set a password before disconnecting it.
            </p>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {PROVIDERS.filter((provider) => !connected.has(provider.provider)).map((provider) => (
              <Button
                key={provider.strategy}
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => void handleConnection(() => onConnect(provider.strategy))}
              >
                Connect {provider.label}
              </Button>
            ))}
          </div>

          {connectionError ? <p className="text-sm text-destructive">{connectionError}</p> : null}
        </div>
      </SettingsCard>
    </div>
  )
}

function formatLastActive(date: Date | null | undefined): string {
  if (!date) return 'Last active recently'
  return `Last active ${date.toLocaleString()}`
}

/** Binds the view to Clerk's password, session, and external-account APIs. */
export function SecurityPanel({ user }: { user: ClerkUser }) {
  const { session } = useSession()
  const [sessions, setSessions] = React.useState<Array<SessionRow>>([])
  const [loading, setLoading] = React.useState(true)

  const currentSessionId = session?.id

  const loadSessions = React.useCallback(async () => {
    setLoading(true)
    try {
      const all = await user.getSessions()
      setSessions(
        all
          // The device you're reading this on stays out of the list.
          .filter((entry) => entry.id !== currentSessionId)
          .map((entry) => {
            const activity = entry.latestActivity
            const place = [activity.city, activity.country].filter(Boolean).join(', ')
            const device = [activity.browserName, activity.deviceType, place]
              .filter(Boolean)
              .join(' · ')
            return {
              id: entry.id,
              device: device || 'Unknown device',
              lastActive: formatLastActive(entry.lastActiveAt),
            }
          }),
      )
    } finally {
      setLoading(false)
    }
  }, [user, currentSessionId])

  React.useEffect(() => {
    void loadSessions()
  }, [loadSessions])

  const connections: Array<ConnectionRow> = user.externalAccounts.map((account) => ({
    id: account.id,
    provider: account.provider,
    label: account.emailAddress || account.username || account.provider,
  }))

  return (
    <SecurityView
      hasPassword={user.passwordEnabled}
      onSavePassword={({ currentPassword, newPassword }) =>
        user.updatePassword({
          ...(user.passwordEnabled ? { currentPassword } : {}),
          newPassword,
        })
      }
      sessions={sessions}
      sessionsLoading={loading}
      onRevokeSession={async (id) => {
        const all = await user.getSessions()
        await all.find((entry) => entry.id === id)?.revoke()
      }}
      connections={connections}
      onConnect={async (strategy) => {
        const origin = window.location.origin
        await user.createExternalAccount({
          strategy: strategy as Parameters<ClerkUser['createExternalAccount']>[0]['strategy'],
          redirectUrl: `${origin}/settings/profile`,
        })
      }}
      onDisconnect={async (id) => {
        await user.externalAccounts.find((account) => account.id === id)?.destroy()
        await user.reload()
      }}
    />
  )
}
