import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DangerZone } from './danger-zone'

function open(onSuspend = vi.fn().mockResolvedValue(undefined)) {
  render(<DangerZone organizationName="Acme" canManage onSuspend={onSuspend} />)
  fireEvent.click(screen.getByRole('button', { name: 'Suspend organization' }))
  return onSuspend
}

const confirmButton = () =>
  screen.getAllByRole('button', { name: 'Suspend organization' }).at(-1) as HTMLButtonElement

describe('DangerZone', () => {
  it('keeps confirm disabled until the typed name matches exactly', async () => {
    open()

    await waitFor(() => expect(screen.getByLabelText(/Type/)).toBeTruthy())
    expect(confirmButton().hasAttribute('disabled')).toBe(true)

    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'acme' } })
    expect(confirmButton().hasAttribute('disabled')).toBe(true)

    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'Acme' } })
    await waitFor(() => expect(confirmButton().hasAttribute('disabled')).toBe(false))
  })

  it('suspends once confirmed', async () => {
    const onSuspend = open()

    await waitFor(() => expect(screen.getByLabelText(/Type/)).toBeTruthy())
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'Acme' } })
    fireEvent.click(confirmButton())

    await waitFor(() => expect(onSuspend).toHaveBeenCalled())
  })

  it('surfaces a failure without closing the dialog', async () => {
    const onSuspend = vi.fn().mockRejectedValue(new Error('Nope'))
    render(<DangerZone organizationName="Acme" canManage onSuspend={onSuspend} />)
    fireEvent.click(screen.getByRole('button', { name: 'Suspend organization' }))

    await waitFor(() => expect(screen.getByLabelText(/Type/)).toBeTruthy())
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'Acme' } })
    fireEvent.click(confirmButton())

    await waitFor(() => expect(screen.getByText('Nope')).toBeTruthy())
    expect(screen.getByLabelText(/Type/)).toBeTruthy()
  })

  it('renders nothing without management rights', () => {
    const { container } = render(
      <DangerZone organizationName="Acme" canManage={false} onSuspend={vi.fn()} />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('states that data is retained', () => {
    render(<DangerZone organizationName="Acme" canManage onSuspend={vi.fn()} />)
    expect(screen.getByText(/retains all of this organization’s data/)).toBeTruthy()
  })
})
