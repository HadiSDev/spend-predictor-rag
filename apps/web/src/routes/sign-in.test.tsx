import type { ComponentType } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

// A mutable stand-in for Clerk's future `signIn` resource, reconfigured per test.
const clerk = {
  password: vi.fn(),
  finalize: vi.fn(),
  sso: vi.fn(),
  emailCode: { sendCode: vi.fn(), verifyCode: vi.fn() },
  status: 'needs_first_factor' as string,
}

vi.mock('@clerk/tanstack-react-start', () => ({
  useSignIn: () => ({ signIn: clerk, fetchStatus: 'idle' }),
  useAuth: () => ({ isSignedIn: false }),
  useClerk: () => ({ signOut: vi.fn().mockResolvedValue(undefined) }),
}))

// Keep createFileRoute real; stub navigation.
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

import { Route } from './sign-in'

const SignInPage = Route.options.component as unknown as ComponentType

beforeEach(() => {
  vi.clearAllMocks()
  clerk.status = 'needs_first_factor'
})

describe('sign-in branding', () => {
  it('shows the Steelyard lockup, rendered rather than typed', () => {
    const { container } = render(<SignInPage />)

    expect(screen.getByRole('img', { name: 'Steelyard' }).tagName.toLowerCase()).toBe('svg')
    expect(container.textContent).not.toMatch(/steelyard/i)
  })
})

describe('sign-in (password)', () => {
  it('renders and surfaces an error when Clerk rejects the credentials', async () => {
    clerk.password.mockResolvedValue({ error: { message: 'Invalid email or password' } })

    render(<SignInPage />)
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.com' } })
    // "Password" also names the tab; scope to the input.
    fireEvent.change(screen.getByLabelText('Password', { selector: 'input' }), {
      target: { value: 'wrong' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('Invalid email or password')
    expect(clerk.finalize).not.toHaveBeenCalled()
  })
})

describe('sign-in (passwordless email code)', () => {
  it('sends a code then finalizes the session on verification', async () => {
    clerk.status = 'complete'
    clerk.emailCode.sendCode.mockResolvedValue({ error: null })
    clerk.emailCode.verifyCode.mockResolvedValue({ error: null })
    clerk.finalize.mockResolvedValue({ error: null })

    render(<SignInPage />)

    // Switch to the passwordless tab.
    fireEvent.click(screen.getByRole('tab', { name: 'Email code' }))

    // Step 1: request a code.
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'a@b.com' } })
    fireEvent.click(screen.getByRole('button', { name: /Email me a code/ }))
    await waitFor(() =>
      expect(clerk.emailCode.sendCode).toHaveBeenCalledWith({ emailAddress: 'a@b.com' }),
    )

    // Step 2: the completed code submits on its own — no click. A code arrives
    // by paste from an email, and asking for a button press after it is already
    // whole is the click this field exists to remove.
    fireEvent.change(await screen.findByLabelText('Verification code'), {
      target: { value: '123456' },
    })

    await waitFor(() => expect(clerk.emailCode.verifyCode).toHaveBeenCalledWith({ code: '123456' }))
    await waitFor(() => expect(clerk.finalize).toHaveBeenCalledTimes(1))
    expect(clerk.emailCode.verifyCode).toHaveBeenCalledTimes(1)
  })

  it('keeps the button as the retry path after a rejected code', async () => {
    clerk.status = 'complete'
    clerk.emailCode.sendCode.mockResolvedValue({ error: null })
    clerk.emailCode.verifyCode.mockResolvedValue({ error: { message: 'Incorrect code' } })

    render(<SignInPage />)
    fireEvent.click(screen.getByRole('tab', { name: 'Email code' }))
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'a@b.com' } })
    fireEvent.click(screen.getByRole('button', { name: /Email me a code/ }))

    const field = await screen.findByLabelText('Verification code')
    fireEvent.change(field, { target: { value: '000000' } })

    // Auto-submit ran and Clerk rejected it.
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(clerk.emailCode.verifyCode).toHaveBeenCalledTimes(1)

    // The same code is still on screen, so completion does not re-fire; the
    // button is what resubmits it.
    fireEvent.click(screen.getByRole('button', { name: /Verify & sign in/ }))
    await waitFor(() => expect(clerk.emailCode.verifyCode).toHaveBeenCalledTimes(2))
    expect(clerk.finalize).not.toHaveBeenCalled()
  })
})
