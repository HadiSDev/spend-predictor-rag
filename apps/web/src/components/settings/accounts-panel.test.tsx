import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { AccountsPanel } from './accounts-panel'
import type { AccountsPanelProps } from './accounts-panel'
import type { ErpAccountRead } from '#/lib/types'

/** Base UI's Switch renders a `span[role=switch]`, not an input — state lives
 *  on `aria-checked` / `aria-disabled`, never on `.checked` or `.disabled`. */
function switchState(name: string) {
  const el = screen.getByRole('switch', { name })
  return {
    on: el.getAttribute('aria-checked') === 'true',
    disabled: el.getAttribute('aria-disabled') === 'true',
  }
}

function account(overrides: Partial<ErpAccountRead> = {}): ErpAccountRead {
  return {
    id: 'a1',
    erp_integration_id: 'i1',
    erp_account_code: '6010',
    erp_account_name: 'Cloud Hosting',
    erp_account_type: 'expense',
    parent_code: null,
    is_active: true,
    sync_enabled: true,
    with_vat: true,
    ...overrides,
  }
}

const ACCOUNTS = [
  account({ id: 'a1', erp_account_code: '6010', erp_account_name: 'Cloud Hosting' }),
  account({ id: 'a2', erp_account_code: '6020', erp_account_name: 'Software', with_vat: false }),
  account({
    id: 'a3',
    erp_account_code: '2100',
    erp_account_name: 'Accounts Payable',
    erp_account_type: 'liability',
    sync_enabled: false,
    with_vat: false,
  }),
]

function props(overrides: Partial<AccountsPanelProps> = {}): AccountsPanelProps {
  return {
    companyName: 'Acme A/S',
    accounts: ACCOUNTS,
    loading: false,
    canManage: true,
    hasIntegration: true,
    onToggle: vi.fn().mockResolvedValue({}),
    onRefresh: vi.fn().mockResolvedValue({ seen: 3, added: 0 }),
    onBack: vi.fn(),
    ...overrides,
  }
}

function setup(overrides: Partial<AccountsPanelProps> = {}) {
  const p = props(overrides)
  render(<AccountsPanel {...p} />)
  return p
}

describe('AccountsPanel', () => {
  it('lists accounts with both settings', () => {
    setup()
    expect(screen.getByText('Cloud Hosting')).toBeTruthy()
    expect(screen.getByText('3 accounts · 2 synced')).toBeTruthy()
    expect(switchState('Sync 6010').on).toBe(true)
    expect(switchState('Sync 2100').on).toBe(false)
    expect(switchState('VAT on 6020').on).toBe(false)
  })

  it('explains what each toggle does, since neither is self-evident', () => {
    setup()
    expect(screen.getByText(/keeps everything already synced/)).toBeTruthy()
    expect(screen.getByText(/recalculates nothing on its own/)).toBeTruthy()
  })

  it('patches only the account whose switch moved', async () => {
    const p = setup()
    fireEvent.click(screen.getByRole('switch', { name: 'VAT on 6010' }))

    await waitFor(() => expect(p.onToggle).toHaveBeenCalledTimes(1))
    expect(p.onToggle).toHaveBeenCalledWith('a1', { with_vat: false })
  })

  it('surfaces a failed toggle against its own row', async () => {
    const onToggle = vi.fn().mockRejectedValue(new Error('Insufficient permissions'))
    setup({ onToggle })

    fireEvent.click(screen.getByRole('switch', { name: 'Sync 6010' }))

    // Against the row, not as a page-level banner — with 25 rows a global
    // error says nothing about which one failed.
    const row = screen.getByText('Cloud Hosting').closest('tr')!
    expect(await within(row).findByText('Insufficient permissions')).toBeTruthy()
  })

  it('searches by code and by name', () => {
    setup()
    fireEvent.change(screen.getByLabelText('Search accounts'), { target: { value: 'payable' } })
    expect(screen.getByText('Accounts Payable')).toBeTruthy()
    expect(screen.queryByText('Cloud Hosting')).toBeNull()

    fireEvent.change(screen.getByLabelText('Search accounts'), { target: { value: '6010' } })
    expect(screen.getByText('Cloud Hosting')).toBeTruthy()
    expect(screen.queryByText('Accounts Payable')).toBeNull()
  })

  it('scopes a bulk action to the rows a search leaves visible', async () => {
    const p = setup()
    fireEvent.change(screen.getByLabelText('Search accounts'), { target: { value: 'payable' } })

    // The count is on the control, so a filtered view cannot be mistaken for
    // the whole chart.
    fireEvent.click(screen.getByRole('button', { name: 'Enable 1 shown' }))

    await waitFor(() => expect(p.onToggle).toHaveBeenCalledTimes(1))
    expect(p.onToggle).toHaveBeenCalledWith('a3', { sync_enabled: true })
  })

  it('skips accounts a bulk action would not change', async () => {
    const p = setup()
    // 6010 and 6020 are already enabled; only 2100 needs the patch.
    fireEvent.click(screen.getByRole('button', { name: 'Enable 3 shown' }))

    await waitFor(() => expect(p.onToggle).toHaveBeenCalledTimes(1))
    expect(p.onToggle).toHaveBeenCalledWith('a3', { sync_enabled: true })
  })

  it('reports what a refresh found', async () => {
    const onRefresh = vi.fn().mockResolvedValue({ seen: 25, added: 3 })
    setup({ onRefresh })

    fireEvent.click(screen.getByRole('button', { name: /Refresh from ERP/ }))

    expect(await screen.findByText('25 accounts seen, 3 added.')).toBeTruthy()
  })

  it('says so when a refresh found nothing new', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /Refresh from ERP/ }))
    expect(await screen.findByText('3 accounts seen, none new.')).toBeTruthy()
  })

  it('invites a refresh when the chart has never been fetched', () => {
    setup({ accounts: [] })
    expect(screen.getByText(/No accounts fetched yet/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Refresh from ERP/ })).toBeTruthy()
  })

  it('says there is nothing to manage without an integration', () => {
    setup({ accounts: [], hasIntegration: false })
    expect(screen.getByText(/No ERP connection/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Refresh from ERP/ })).toBeNull()
  })

  it('disables every write control for a non-manager', () => {
    setup({ canManage: false })

    expect(switchState('Sync 6010').disabled).toBe(true)
    expect(switchState('VAT on 6010').disabled).toBe(true)
    expect(screen.getByRole('button', { name: /Refresh from ERP/ }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: 'Enable 3 shown' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByText(/read-only access/)).toBeTruthy()
  })

  it('shows placeholders while loading', () => {
    const { container } = render(<AccountsPanel {...props({ loading: true })} />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })

  it('offers a way back to the companies list', () => {
    const p = setup()
    fireEvent.click(screen.getByRole('button', { name: /Companies/ }))
    expect(p.onBack).toHaveBeenCalled()
  })
})
