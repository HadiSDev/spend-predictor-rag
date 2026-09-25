import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ApiError } from '#/lib/api/api-client'
import type * as ApiClientModule from '#/lib/api/api-client'
import {
  AuthProvider,
  canManageCompanies,
  canManageOrganization,
  usePrincipal,
} from './auth'
import type { Principal } from './auth'

let activeOrgId: string | null = 'org_acme'

const signOut = vi.fn()

vi.mock('@clerk/tanstack-react-start', () => ({
  useAuth: () => ({ orgId: activeOrgId, getToken: async () => 'token' }),
  useClerk: () => ({ signOut }),
}))

const get = vi.fn(async () => ({
  id: 'user_1',
  email: 'hadi@example.com',
  name: 'Hadi',
  role: 'admin',
  is_system_admin: false,
  organization_id: activeOrgId,
}))

vi.mock('#/lib/api/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiClientModule>()),
  createApiClient: () => ({ get }),
}))

function Probe() {
  const principal = usePrincipal()
  return <div data-testid="org">{principal.organizationId}</div>
}

function tree(client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  get.mockClear()
  signOut.mockClear()
})

describe('AuthProvider org scope', () => {
  it('discards cached tenant data and reloads the principal when the org changes', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    client.setQueryData(['reports', 'entries-summary'], { rows: ['acme'] })

    const { rerender } = render(tree(client))
    await waitFor(() =>
      expect(screen.getByTestId('org').textContent).toBe('org_acme'),
    )
    expect(get).toHaveBeenCalledTimes(1)

    activeOrgId = 'org_bolt'
    rerender(tree(client))

    await waitFor(() =>
      expect(screen.getByTestId('org').textContent).toBe('org_bolt'),
    )
    expect(client.getQueryData(['reports', 'entries-summary'])).toBeUndefined()
    expect(get).toHaveBeenCalledTimes(2)
  })
})

describe('AuthProvider failure states', () => {
  function renderWithError(error: unknown) {
    get.mockRejectedValueOnce(error)
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(tree(client))
  }

  it('names a suspended organization instead of a generic failure', async () => {
    renderWithError(
      new ApiError(403, 'failed', { detail: 'Organization is suspended' }),
    )

    await waitFor(() =>
      expect(screen.getByText('Organization suspended')).toBeTruthy(),
    )
    screen.getByRole('button', { name: 'Sign out' }).click()
    expect(signOut).toHaveBeenCalled()
  })

  it('shows the generic screen for any other failure', async () => {
    renderWithError(new ApiError(500, 'failed', undefined))

    await waitFor(() =>
      expect(screen.getByText('Couldn’t load your account')).toBeTruthy(),
    )
    expect(screen.queryByText('Organization suspended')).toBeNull()
  })

  it('does not mistake an unrelated 403 for a suspension', async () => {
    renderWithError(
      new ApiError(403, 'failed', { detail: 'Insufficient permissions' }),
    )

    await waitFor(() =>
      expect(screen.getByText('Couldn’t load your account')).toBeTruthy(),
    )
  })

  it('offers a working retry control that refetches the principal', async () => {
    renderWithError(new ApiError(500, 'failed', undefined))

    await waitFor(() =>
      expect(screen.getByText('Couldn’t load your account')).toBeTruthy(),
    )
    expect(get).toHaveBeenCalledTimes(1)

    screen.getByRole('button', { name: 'Try again' }).click()

    await waitFor(() =>
      expect(screen.getByTestId('org').textContent).toBe(activeOrgId),
    )
    expect(get).toHaveBeenCalledTimes(2)
  })
})

describe('role gates', () => {
  function principal(overrides: Partial<Principal> = {}): Principal {
    return {
      id: 'u1',
      email: 'a@b.com',
      name: 'A B',
      role: 'member',
      isSystemAdmin: false,
      organizationId: 'org1',
      ...overrides,
    }
  }

  it.each([
    ['admin', true],
    ['moderator', false],
    ['member', false],
    ['viewer', false],
  ] as const)('canManageOrganization(%s) === %s', (role, expected) => {
    expect(canManageOrganization(principal({ role }))).toBe(expected)
  })

  it.each([
    ['admin', true],
    ['moderator', true],
    ['member', false],
    ['viewer', false],
  ] as const)('canManageCompanies(%s) === %s', (role, expected) => {
    expect(canManageCompanies(principal({ role }))).toBe(expected)
  })

  it('lets a system admin manage everything regardless of org role', () => {
    const sysadmin = principal({ role: 'viewer', isSystemAdmin: true })
    expect(canManageOrganization(sysadmin)).toBe(true)
    expect(canManageCompanies(sysadmin)).toBe(true)
  })
})
