import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ToastProvider } from '#/components/ui'
import { ApiError } from '#/lib/api/api-client'
import { ProfilePanel, validateImage } from './profile-panel'

function renderPanel(
  overrides: Partial<Parameters<typeof ProfilePanel>[0]> = {},
) {
  const onSave = overrides.onSave ?? vi.fn().mockResolvedValue(undefined)
  render(
    <ToastProvider>
      <ProfilePanel
        defaultValues={{ firstName: 'Ada', lastName: 'Lovelace' }}
        displayName="Ada Lovelace"
        email="ada@example.com"
        onSave={onSave}
        onUploadImage={vi.fn().mockResolvedValue(undefined)}
        onRemoveImage={vi.fn().mockResolvedValue(undefined)}
        {...overrides}
      />
    </ToastProvider>,
  )
  return { onSave }
}

const save = () => screen.getByRole('button', { name: 'Save changes' })

describe('ProfilePanel', () => {
  it('cannot be submitted while pristine', () => {
    renderPanel()
    expect(save().hasAttribute('disabled')).toBe(true)
  })

  it('enables save once a field changes, then saves', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    renderPanel({ onSave })

    fireEvent.change(screen.getByLabelText('First name'), {
      target: { value: 'Grace' },
    })
    await waitFor(() => expect(save().hasAttribute('disabled')).toBe(false))

    fireEvent.click(save())

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        firstName: 'Grace',
        lastName: 'Lovelace',
      }),
    )
    await waitFor(() => expect(save().hasAttribute('disabled')).toBe(true))
  })

  it('shows a pending state while the save is in flight', async () => {
    let resolve: () => void = () => {}
    const onSave = vi
      .fn()
      .mockReturnValue(new Promise<void>((r) => (resolve = r)))
    renderPanel({ onSave })

    fireEvent.change(screen.getByLabelText('First name'), {
      target: { value: 'Grace' },
    })
    fireEvent.click(save())

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Saving…' })).toBeTruthy(),
    )
    expect(
      screen.getByRole('button', { name: 'Saving…' }).hasAttribute('disabled'),
    ).toBe(true)

    resolve()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save changes' })).toBeTruthy(),
    )
  })

  it('surfaces a failure and keeps what the user typed', async () => {
    const onSave = vi
      .fn()
      .mockRejectedValue(
        new ApiError(403, 'generic', { detail: 'Insufficient permissions' }),
      )
    renderPanel({ onSave })

    fireEvent.change(screen.getByLabelText('First name'), {
      target: { value: 'Grace' },
    })
    fireEvent.click(save())

    await waitFor(() =>
      expect(
        screen.getAllByText('Insufficient permissions').length,
      ).toBeGreaterThan(0),
    )
    expect(screen.getByLabelText<HTMLInputElement>('First name').value).toBe(
      'Grace',
    )
    expect(
      screen
        .getByRole('button', { name: 'Save changes' })
        .hasAttribute('disabled'),
    ).toBe(false)
  })

  it('rejects an oversized or unsupported image before uploading', () => {
    const big = new File(['x'], 'big.png', { type: 'image/png' })
    Object.defineProperty(big, 'size', { value: 6 * 1024 * 1024 })
    expect(validateImage(big)).toMatch(/5 MB/)

    const pdf = new File(['x'], 'doc.pdf', { type: 'application/pdf' })
    expect(validateImage(pdf)).toMatch(/PNG/)

    const ok = new File(['x'], 'me.png', { type: 'image/png' })
    expect(validateImage(ok)).toBeNull()
  })

  it('uploads a valid image', async () => {
    const onUploadImage = vi.fn().mockResolvedValue(undefined)
    renderPanel({ onUploadImage })

    const file = new File(['x'], 'me.png', { type: 'image/png' })
    fireEvent.change(screen.getByLabelText('Profile photo'), {
      target: { files: [file] },
    })

    await waitFor(() => expect(onUploadImage).toHaveBeenCalledWith(file))
  })
})
