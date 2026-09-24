import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ToastProvider } from '#/components/ui'
import { OrgSwitcher } from './org-switcher'

const navigate = vi.fn()
const setActive = vi.fn()

let activeOrgId: string | null = 'org_acme'
let orgsLoaded = true
let orgRows: Array<{ organization: { id: string; name: string } }> = []

vi.mock('@clerk/tanstack-react-start', () => ({
  useAuth: () => ({ orgId: activeOrgId }),
  useOrganizationList: () => ({
    isLoaded: orgsLoaded,
    userMemberships: { data: orgRows },
    setActive,
  }),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
}))

function membership(id: string, name: string) {
  return { organization: { id, name } }
}

function renderSwitcher() {
  return render(
    <ToastProvider>
      <OrgSwitcher />
    </ToastProvider>,
  )
}

/** Opens the popup the way a pointer does — Base UI listens below `click`. */
function openSwitcher() {
  const trigger = screen.getByRole('combobox', { name: 'Switch organization' })
  trigger.focus()
  fireEvent.pointerDown(trigger, { pointerType: 'mouse' })
  fireEvent.mouseDown(trigger)
  fireEvent.mouseUp(trigger)
  fireEvent.click(trigger)
  return trigger
}

beforeEach(() => {
  navigate.mockReset()
  setActive.mockReset().mockResolvedValue(undefined)
  activeOrgId = 'org_acme'
  orgsLoaded = true
  orgRows = [membership('org_acme', 'Acme A/S'), membership('org_bolt', 'Bolt Industries')]
})

describe('OrgSwitcher', () => {
  it('activates the organization the user picks', async () => {
    renderSwitcher()
    expect(screen.getByRole('combobox', { name: 'Switch organization' }).textContent).toContain(
      'Acme A/S',
    )

    openSwitcher()
    fireEvent.click(await screen.findByRole('option', { name: 'Bolt Industries' }))

    await waitFor(() => expect(setActive).toHaveBeenCalledTimes(1))
    expect(setActive).toHaveBeenCalledWith({ organization: 'org_bolt' })
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/' }))
  })

  it('filters the membership list as the user types', async () => {
    renderSwitcher()
    openSwitcher()
    await screen.findByRole('option', { name: 'Acme A/S' })

    fireEvent.change(screen.getByRole('combobox', { name: 'Search organizations' }), {
      target: { value: 'bolt' },
    })

    await waitFor(() => expect(screen.queryByRole('option', { name: 'Acme A/S' })).toBeNull())
    expect(screen.getByRole('option', { name: 'Bolt Industries' })).toBeTruthy()
  })

  it('renders a plain label when the user belongs to one organization', () => {
    orgRows = [membership('org_acme', 'Acme A/S')]
    renderSwitcher()

    expect(screen.getByText('Acme A/S')).toBeTruthy()
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('renders a placeholder while memberships are loading', () => {
    orgsLoaded = false
    orgRows = []
    renderSwitcher()

    expect(screen.getByTestId('org-switcher-loading')).toBeTruthy()
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('keeps the current organization and reports the error when activation fails', async () => {
    setActive.mockRejectedValue(new Error('nope'))
    renderSwitcher()

    openSwitcher()
    fireEvent.click(await screen.findByRole('option', { name: 'Bolt Industries' }))

    expect(await screen.findByText('Couldn’t switch organization')).toBeTruthy()
    expect(navigate).not.toHaveBeenCalled()
    // Clerk never changed the active org, so the trigger still shows the old one.
    expect(screen.getByRole('combobox', { name: 'Switch organization' }).textContent).toContain(
      'Acme A/S',
    )
  })
})
