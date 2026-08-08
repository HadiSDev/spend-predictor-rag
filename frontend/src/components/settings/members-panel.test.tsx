import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MembersView, blockedReason, roleLabel } from './members-panel'
import type { MemberRow, MembersViewProps } from './members-panel'

const ROLES = [
  { value: 'org:admin', label: 'Admin' },
  { value: 'org:member', label: 'Member' },
]

const ADMIN: MemberRow = {
  id: 'm1',
  name: 'Ada Lovelace',
  email: 'ada@example.com',
  role: 'org:admin',
  isSelf: false,
}
const MEMBER: MemberRow = {
  id: 'm2',
  name: 'Grace Hopper',
  email: 'grace@example.com',
  role: 'org:member',
  isSelf: false,
}

function renderView(overrides: Partial<MembersViewProps> = {}) {
  const props: MembersViewProps = {
    members: [ADMIN, MEMBER],
    invitations: [],
    roles: ROLES,
    canManage: true,
    onChangeRole: vi.fn().mockResolvedValue(undefined),
    onRemove: vi.fn().mockResolvedValue(undefined),
    onInvite: vi.fn().mockResolvedValue(undefined),
    onRevokeInvitation: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
  render(<MembersView {...props} />)
  return props
}

describe('blockedReason', () => {
  it('blocks changing your own role', () => {
    const self = { ...MEMBER, isSelf: true }
    expect(blockedReason(self, [ADMIN, self])).toMatch(/your own role/)
  })

  it('blocks touching the last admin', () => {
    expect(blockedReason(ADMIN, [ADMIN, MEMBER])).toMatch(/only admin/)
  })

  it('allows an admin when another admin exists', () => {
    const second = { ...MEMBER, role: 'org:admin' }
    expect(blockedReason(ADMIN, [ADMIN, second])).toBeNull()
  })
})

describe('roleLabel', () => {
  it('uses the label the Clerk instance reports', () => {
    expect(roleLabel('org:admin', ROLES)).toBe('Admin')
  })

  it('strips the namespace for a role the instance did not list', () => {
    expect(roleLabel('org:billing_manager', ROLES)).toBe('billing_manager')
  })
})

describe('MembersView', () => {
  it('lists members with their roles', () => {
    renderView()

    expect(screen.getByText('Ada Lovelace')).toBeTruthy()
    expect(screen.getByText('grace@example.com')).toBeTruthy()
  })

  it('offers no role control for the last admin, and says why', () => {
    renderView()

    expect(screen.queryByLabelText('Role for ada@example.com')).toBeNull()
    expect(screen.getByText(/only admin/)).toBeTruthy()
    // The manageable member still gets one.
    expect(screen.getByLabelText('Role for grace@example.com')).toBeTruthy()
  })

  it('shows the role label in the select trigger, not the Clerk key', () => {
    renderView()

    expect(screen.getByLabelText('Role for grace@example.com').textContent).toBe('Member')
    expect(screen.getByLabelText('Invite role').textContent).toBe('Member')
  })

  it('shows role labels as badges where the select is not offered', () => {
    renderView({ canManage: false })

    expect(screen.getByText('Admin')).toBeTruthy()
    expect(screen.getByText('Member')).toBeTruthy()
    expect(screen.queryByText('org:admin')).toBeNull()
    expect(screen.queryByText('org:member')).toBeNull()
  })

  it('removes a member only after confirmation', async () => {
    const props = renderView()

    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(props.onRemove).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(props.onRemove).toHaveBeenCalledWith('m2'))
  })

  it('sends an invitation and clears the field', async () => {
    const props = renderView()

    fireEvent.change(screen.getByLabelText('Invite email address'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send invitation' }))

    await waitFor(() =>
      expect(props.onInvite).toHaveBeenCalledWith('new@example.com', 'org:member'),
    )
    await waitFor(() =>
      expect(screen.getByLabelText<HTMLInputElement>('Invite email address').value).toBe(''),
    )
  })

  it('explains what to do when the Clerk instance has invitations disabled', async () => {
    // Clerk's own message is "contact support", with no dashboard setting to
    // point at — so the panel says what the admin can actually do.
    const onInvite = vi.fn().mockRejectedValue({
      errors: [
        {
          code: 'invitations_not_supported_in_organization',
          longMessage: 'This organization doesn’t support email invitations.',
        },
      ],
    })
    renderView({ onInvite })

    fireEvent.change(screen.getByLabelText('Invite email address'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send invitation' }))

    await waitFor(() => expect(screen.getByText(/aren’t enabled for this Clerk instance/)).toBeTruthy())
    expect(screen.getByText(/add people from the Clerk dashboard/)).toBeTruthy()
  })

  it('surfaces a rejected invitation on the form', async () => {
    const onInvite = vi.fn().mockRejectedValue({
      errors: [{ longMessage: 'That user is already a member of this organization.' }],
    })
    renderView({ onInvite })

    fireEvent.change(screen.getByLabelText('Invite email address'), {
      target: { value: 'ada@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send invitation' }))

    await waitFor(() =>
      expect(screen.getByText('That user is already a member of this organization.')).toBeTruthy(),
    )
  })

  it('presents an invitation with a heading, a readable status, and its role', () => {
    renderView({
      invitations: [{ id: 'i1', email: 'new@example.com', role: 'org:member', status: 'pending' }],
    })

    expect(screen.getByText('Pending invitations')).toBeTruthy()
    expect(screen.getByText('new@example.com')).toBeTruthy()
    // Clerk's raw lowercase token is never shown as-is.
    expect(screen.getByText('Pending')).toBeTruthy()
    expect(screen.queryByText('pending')).toBeNull()
  })

  it('revokes a pending invitation', async () => {
    const props = renderView({
      invitations: [{ id: 'i1', email: 'new@example.com', role: 'org:member', status: 'pending' }],
    })

    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }))

    await waitFor(() => expect(props.onRevokeInvitation).toHaveBeenCalledWith('i1'))
  })

  it('is read-only without management rights', () => {
    renderView({ canManage: false })

    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull()
    expect(screen.queryByLabelText('Invite email address')).toBeNull()
    expect(screen.getByText(/Only an organization admin/)).toBeTruthy()
  })
})
