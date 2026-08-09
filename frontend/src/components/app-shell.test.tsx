import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type * as RouterModule from '@tanstack/react-router'
import { AppSidebar, isNavItemActive } from './app-shell'

// Keep the sidebar presentational in tests: `Link` becomes a plain anchor so no
// router context is needed, matching how sign-in.test.tsx stubs navigation.
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof RouterModule>()
  return {
    ...actual,
    Link: ({ to, children, ...props }: { to: string; children: ReactNode }) => (
      <a href={to} {...props}>
        {children}
      </a>
    ),
  }
})

// The org switcher is Clerk-backed and covered by its own test.
vi.mock('#/components/org-switcher', () => ({ OrgSwitcher: () => null }))

describe('isNavItemActive', () => {
  it('matches the dashboard exactly', () => {
    expect(isNavItemActive('/', '/')).toBe(true)
    expect(isNavItemActive('/settings', '/')).toBe(false)
  })

  it('matches a section and its children', () => {
    expect(isNavItemActive('/settings', '/settings')).toBe(true)
    expect(isNavItemActive('/settings/companies', '/settings')).toBe(true)
    // A sibling path that merely shares a prefix is not a match.
    expect(isNavItemActive('/settings-other', '/settings')).toBe(false)
  })
})

describe('AppSidebar', () => {
  it('renders Settings as an enabled link', () => {
    render(<AppSidebar pathname="/" />)

    const settings = screen.getByRole('link', { name: 'Settings' })
    expect(settings.getAttribute('href')).toBe('/settings')
  })

  it('marks the entry matching the current route as active', () => {
    render(<AppSidebar pathname="/settings/companies" />)

    expect(screen.getByRole('link', { name: 'Settings' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: 'Dashboard' }).getAttribute('aria-current')).toBeNull()
  })

  it('keeps pages that do not exist yet disabled and unlinked', () => {
    render(<AppSidebar pathname="/" />)

    expect(screen.queryByRole('link', { name: 'Vendors' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Vendors' }).hasAttribute('disabled')).toBe(true)
  })

  it('links Spend Lines to its page, and no longer promises an Invoices one', () => {
    render(<AppSidebar pathname="/entries" />)

    // Named for what the page lists. The *path* stays `/entries`: every shared
    // voucher link carries it, and the panel's design rests on those resolving.
    const entries = screen.getByRole('link', { name: 'Spend Lines' })
    expect(entries.getAttribute('href')).toBe('/entries')
    expect(entries.getAttribute('aria-current')).toBe('page')
    // The disabled Invoices placeholder is gone rather than merely unlinked.
    expect(screen.queryByText('Invoices')).toBeNull()
  })
})
