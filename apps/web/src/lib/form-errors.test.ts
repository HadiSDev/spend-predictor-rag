import { describe, expect, it, vi } from 'vitest'
import { ApiError } from './api/api-client'
import { applyServerError, serverErrorMessage } from './form-errors'

describe('serverErrorMessage', () => {
  it('uses the web API detail', () => {
    expect(
      serverErrorMessage(
        new ApiError(409, 'generic', { detail: 'Slug already in use' }),
      ),
    ).toBe('Slug already in use')
  })

  it('prefers Clerk’s long message', () => {
    const clerkError = {
      errors: [
        { message: 'is taken', longMessage: 'That email address is taken.' },
      ],
    }
    expect(serverErrorMessage(clerkError)).toBe('That email address is taken.')
  })

  it('falls back to a generic message for an unknown failure', () => {
    expect(serverErrorMessage({})).toBe(
      'Something went wrong. Please try again.',
    )
  })
})

describe('applyServerError', () => {
  it('maps a Clerk paramName onto the matching field', () => {
    const setError = vi.fn()
    const error = {
      errors: [
        { message: 'Incorrect password', meta: { paramName: 'password' } },
      ],
    }

    applyServerError(error, setError, { fields: ['password', 'newPassword'] })

    expect(setError).toHaveBeenCalledWith('password', {
      type: 'server',
      message: 'Incorrect password',
    })
  })

  it('maps a 422 detail onto the field it names', () => {
    const setError = vi.fn()
    const error = new ApiError(422, 'generic', {
      detail: [{ msg: 'Field required', loc: ['body', 'name'] }],
    })

    applyServerError(error, setError, { fields: ['name'] })

    expect(setError).toHaveBeenCalledWith('name', {
      type: 'server',
      message: 'name: Field required',
    })
  })

  it('honours an explicit mapping for errors that name no field', () => {
    const setError = vi.fn()
    const error = new ApiError(409, 'generic', {
      detail: 'Slug already in use',
    })

    applyServerError(error, setError, {
      fields: ['name', 'slug'],
      fieldFor: (e) =>
        e instanceof ApiError && e.status === 409 ? 'slug' : undefined,
    })

    expect(setError).toHaveBeenCalledWith('slug', {
      type: 'server',
      message: 'Slug already in use',
    })
  })

  it('falls back to a form-level error', () => {
    const setError = vi.fn()
    const error = new ApiError(403, 'generic', {
      detail: 'Insufficient permissions',
    })

    const message = applyServerError(error, setError, { fields: ['name'] })

    expect(message).toBe('Insufficient permissions')
    expect(setError).toHaveBeenCalledWith('root', {
      type: 'server',
      message: 'Insufficient permissions',
    })
  })
})
