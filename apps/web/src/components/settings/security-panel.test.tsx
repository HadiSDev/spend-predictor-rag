import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ToastProvider } from '#/components/ui'
import { SecurityView } from './security-panel'
import type { SecurityViewProps } from './security-panel'

function renderView(overrides: Partial<SecurityViewProps> = {}) {
  const props: SecurityViewProps = {
    hasPassword: true,
    onSavePassword: vi.fn().mockResolvedValue(undefined),
    sessions: [{ id: 's1', device: 'Chrome · desktop · Copenhagen', lastActive: 'Last active now' }],
    onRevokeSession: vi.fn().mockResolvedValue(undefined),
    connections: [{ id: 'x1', provider: 'google', label: 'ada@example.com' }],
    onConnect: vi.fn().mockResolvedValue(undefined),
    onDisconnect: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
  render(
    <ToastProvider>
      <SecurityView {...props} />
    </ToastProvider>,
  )
  return props
}

describe('SecurityView password', () => {
  it('rejects a mismatched confirmation without calling the server', async () => {
    const onSavePassword = vi.fn().mockResolvedValue(undefined)
    renderView({ onSavePassword })

    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'old-secret' } })
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'new-secret-1' } })
    fireEvent.change(screen.getByLabelText('Confirm new password'), {
      target: { value: 'different-1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }))

    await waitFor(() => expect(screen.getByText('The passwords don’t match.')).toBeTruthy())
    expect(onSavePassword).not.toHaveBeenCalled()
  })

  it('submits a matching password', async () => {
    const onSavePassword = vi.fn().mockResolvedValue(undefined)
    renderView({ onSavePassword })

    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'old-secret' } })
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'new-secret-1' } })
    fireEvent.change(screen.getByLabelText('Confirm new password'), {
      target: { value: 'new-secret-1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }))

    await waitFor(() =>
      expect(onSavePassword).toHaveBeenCalledWith({
        currentPassword: 'old-secret',
        newPassword: 'new-secret-1',
        confirmPassword: 'new-secret-1',
      }),
    )
  })

  it('asks for no current password when none is set', () => {
    renderView({ hasPassword: false, connections: [], sessions: [] })

    expect(screen.queryByLabelText('Current password')).toBeNull()
    expect(screen.getByRole('button', { name: 'Set password' })).toBeTruthy()
  })
})

describe('SecurityView sessions', () => {
  it('revokes a session and drops it from the list', async () => {
    const props = renderView()

    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }))

    await waitFor(() => expect(props.onRevokeSession).toHaveBeenCalledWith('s1'))
    await waitFor(() => expect(screen.getByText('No other devices are signed in.')).toBeTruthy())
  })
})

describe('SecurityView connected accounts', () => {
  it('blocks disconnecting the only sign-in method', () => {
    renderView({ hasPassword: false })

    expect(screen.getByRole('button', { name: 'Disconnect' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByText(/only way to sign in/)).toBeTruthy()
  })

  it('allows disconnecting when a password also exists', async () => {
    const props = renderView({ hasPassword: true })

    fireEvent.click(screen.getByRole('button', { name: 'Disconnect' }))

    await waitFor(() => expect(props.onDisconnect).toHaveBeenCalledWith('x1'))
  })

  it('offers only providers that are not connected yet', () => {
    renderView()

    expect(screen.queryByRole('button', { name: 'Connect Google' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Connect Microsoft' })).toBeTruthy()
  })
})
