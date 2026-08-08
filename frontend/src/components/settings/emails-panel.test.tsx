import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { EmailsView } from './emails-panel'
import type { EmailsViewProps } from './emails-panel'

const EMAILS = [
  { id: 'e1', address: 'ada@example.com', verified: true, primary: true },
  { id: 'e2', address: 'ada@work.example', verified: false, primary: false },
]

function renderView(overrides: Partial<EmailsViewProps> = {}) {
  const props: EmailsViewProps = {
    emails: EMAILS,
    onAdd: vi.fn().mockResolvedValue(undefined),
    onVerify: vi.fn().mockResolvedValue(undefined),
    onResend: vi.fn().mockResolvedValue(undefined),
    onSetPrimary: vi.fn().mockResolvedValue(undefined),
    onRemove: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
  render(<EmailsView {...props} />)
  return props
}

describe('EmailsView', () => {
  it('badges each address and offers no remove on the primary one', () => {
    renderView()

    expect(screen.getByText('Primary')).toBeTruthy()
    expect(screen.getByText('Verified')).toBeTruthy()
    expect(screen.getByText('Unverified')).toBeTruthy()
    // One remove button — for the non-primary address only.
    expect(screen.getAllByRole('button', { name: 'Remove' })).toHaveLength(1)
  })

  it('walks add → verify and returns to the idle form', async () => {
    const props = renderView()

    fireEvent.change(screen.getByLabelText('New email address'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add address' }))

    await waitFor(() => expect(props.onAdd).toHaveBeenCalledWith('new@example.com'))
    await waitFor(() => expect(screen.getByLabelText('Verification code')).toBeTruthy())

    fireEvent.change(screen.getByLabelText('Verification code'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }))

    await waitFor(() => expect(props.onVerify).toHaveBeenCalledWith('123456'))
    await waitFor(() => expect(screen.getByLabelText('New email address')).toBeTruthy())
  })

  it('keeps the address unverified and retryable after a wrong code', async () => {
    const onVerify = vi.fn().mockRejectedValue({
      errors: [{ message: 'is incorrect', longMessage: 'That code is incorrect.' }],
    })
    renderView({ onVerify })

    fireEvent.change(screen.getByLabelText('New email address'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add address' }))
    await waitFor(() => expect(screen.getByLabelText('Verification code')).toBeTruthy())

    fireEvent.change(screen.getByLabelText('Verification code'), { target: { value: '000000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }))

    await waitFor(() => expect(screen.getByText('That code is incorrect.')).toBeTruthy())
    // Still on the verification step, with the code kept so it can be corrected.
    expect(screen.getByLabelText<HTMLInputElement>('Verification code').value).toBe('000000')
    expect(screen.getByRole('button', { name: 'Resend code' })).toBeTruthy()
  })

  it('promotes a verified address to primary', async () => {
    const props = renderView({
      emails: [
        { id: 'e1', address: 'ada@example.com', verified: true, primary: true },
        { id: 'e2', address: 'ada@work.example', verified: true, primary: false },
      ],
    })

    fireEvent.click(screen.getByRole('button', { name: 'Make primary' }))

    await waitFor(() => expect(props.onSetPrimary).toHaveBeenCalledWith('e2'))
  })
})
