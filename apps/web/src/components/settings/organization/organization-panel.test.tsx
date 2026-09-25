import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ToastProvider } from '#/components/ui'
import { ApiError } from '#/lib/api/api-client'
import type { OrganizationRead } from '#/lib/api/types'
import { OrganizationPanel } from './organization-panel'

const ORG: OrganizationRead = {
  id: 'org1',
  name: 'Acme',
  slug: 'acme',
  status: 'active',
  created_at: '2026-01-15T10:00:00Z',
}

function renderPanel(
  overrides: Partial<Parameters<typeof OrganizationPanel>[0]> = {},
) {
  const onSave = overrides.onSave ?? vi.fn().mockResolvedValue(undefined)
  render(
    <ToastProvider>
      <OrganizationPanel organization={ORG} onSave={onSave} {...overrides} />
    </ToastProvider>,
  )
  return { onSave }
}

describe('OrganizationPanel', () => {
  it('lets an admin edit the profile', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    renderPanel({ onSave })

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Acme Group' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({ name: 'Acme Group', slug: 'acme' }),
    )
  })

  it('shows a read-only profile with a reason for non-admins', () => {
    renderPanel({ readOnly: true })

    expect(screen.queryByRole('button', { name: 'Save changes' })).toBeNull()
    expect(screen.getByText(/Only an organization admin/)).toBeTruthy()
    expect(screen.getByText('Acme')).toBeTruthy()
  })

  it('puts a 409 on the slug field and keeps the form editable', async () => {
    const onSave = vi
      .fn()
      .mockRejectedValue(
        new ApiError(409, 'generic', { detail: 'Slug already in use' }),
      )
    renderPanel({ onSave })

    fireEvent.change(screen.getByLabelText('Slug'), {
      target: { value: 'taken' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(screen.getAllByText('Slug already in use').length).toBeGreaterThan(
        0,
      ),
    )
    expect(screen.getByLabelText<HTMLInputElement>('Slug').value).toBe('taken')
    expect(
      screen
        .getByRole('button', { name: 'Save changes' })
        .hasAttribute('disabled'),
    ).toBe(false)
  })

  it('shows status and creation date', () => {
    renderPanel()

    expect(screen.getByText('active')).toBeTruthy()
    expect(screen.getByText('Created')).toBeTruthy()
  })
})
