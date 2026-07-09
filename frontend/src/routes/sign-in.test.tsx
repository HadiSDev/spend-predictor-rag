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

    // Step 2: enter the code and verify.
    fireEvent.change(await screen.findByLabelText('Verification code'), {
      target: { value: '123456' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Verify & sign in/ }))

    await waitFor(() => expect(clerk.emailCode.verifyCode).toHaveBeenCalledWith({ code: '123456' }))
    await waitFor(() => expect(clerk.finalize).toHaveBeenCalledTimes(1))
  })
})
