import { describe, expect, it, vi } from 'vitest'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { ToastProvider } from '#/components/ui'
import type {
  CompanyRead,
  ErpIntegrationRead,
  ErpTypeRead,
} from '#/lib/api/types'
import { CompaniesPanel } from './companies-panel'
import { changedFields } from './company-values'
import type { CompaniesPanelProps } from './companies-panel'

/** The debug connector as `GET /erp-types` reports it. */
const DEBUG_ERP: ErpTypeRead = {
  erp_type: 'mock',
  label: 'Debug ERP',
  credential_fields: [
    {
      name: 'base_url',
      label: 'Base URL',
      required: true,
      secret: false,
      default: 'http://localhost:8001',
    },
    {
      name: 'api_key',
      label: 'API key',
      required: false,
      secret: true,
      default: null,
    },
  ],
}

/** A branded connector, as the catalog reports one that declares brand metadata. */
const BILLY: ErpTypeRead = {
  erp_type: 'billy',
  label: 'Billy',
  brand_slug: 'billy',
  description: 'Danish accounting for small and medium businesses.',
  docs_url: 'https://www.billy.dk/api',
  credential_fields: [
    {
      name: 'access_token',
      label: 'Access token',
      required: true,
      secret: true,
      default: null,
    },
  ],
}

const ACME: CompanyRead = {
  id: 'c1',
  name: 'Acme A/S',
  country_code: 'DK',
  vat_number: 'DK12345678',
  base_currency: 'DKK',
  is_active: true,
  deactivated_at: null,
  spend_tree_id: 'tree1',
  spend_tree_name: 'Default spend tree',
}

const RETIRED: CompanyRead = {
  id: 'c2',
  name: 'Old Holdings',
  country_code: null,
  vat_number: null,
  base_currency: 'EUR',
  is_active: false,
  deactivated_at: '2026-02-01T00:00:00Z',
  spend_tree_id: 'tree1',
  spend_tree_name: 'Default spend tree',
}

/** Acme's connected integration, as `GET /erp-integrations` reports it. */
const INTEGRATION: ErpIntegrationRead = {
  id: 'i1',
  company_id: 'c1',
  erp_type: 'mock',
  label: 'Main',
  connected_at: '2026-03-01T00:00:00Z',
  disconnected_at: null,
  created_at: '2026-03-01T00:00:00Z',
  has_credentials: true,
}

function renderPanel(overrides: Partial<CompaniesPanelProps> = {}) {
  const props: CompaniesPanelProps = {
    companies: [ACME],
    includeInactive: false,
    onIncludeInactiveChange: vi.fn(),
    canManage: true,
    erpTypes: [DEBUG_ERP],
    integrations: [INTEGRATION],
    onCreate: vi.fn().mockResolvedValue(undefined),
    onUpdate: vi.fn().mockResolvedValue(undefined),
    onUpdateIntegration: vi.fn().mockResolvedValue(undefined),
    onConnectIntegration: vi.fn().mockResolvedValue(undefined),
    onSetActive: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn().mockResolvedValue(undefined),
    onRecomputeFx: vi.fn().mockResolvedValue({
      company_id: 'c1',
      base_currency: 'EUR',
      converted: 12,
      unconverted: 1,
      unchanged: 3,
    }),
    onRecategorize: vi.fn().mockResolvedValue({ company_id: 'c1', queued: 28 }),
    ...overrides,
  }
  render(
    <ToastProvider>
      <CompaniesPanel {...props} />
    </ToastProvider>,
  )
  return props
}

/** Pick a reporting currency in the searchable currency field. */
async function chooseCurrency(code: string) {
  const input = screen.getByRole('combobox', { name: 'Reporting currency' })
  fireEvent.click(input)
  fireEvent.change(input, { target: { value: code } })
  fireEvent.click(
    await screen.findByRole('option', { name: new RegExp(`^${code} —`) }),
  )
}

async function chooseCountry(code: string) {
  const input = screen.getByRole('combobox', { name: 'Country' })
  fireEvent.click(input)
  fireEvent.change(input, { target: { value: code } })
  fireEvent.click(
    await screen.findByRole('option', { name: new RegExp(`^${code} —`) }),
  )
}

/** Open a company's row menu and click one of its actions. */
async function clickRowAction(companyName: string, action: string) {
  fireEvent.click(
    screen.getByRole('button', { name: `Actions for ${companyName}` }),
  )
  fireEvent.click(await screen.findByRole('menuitem', { name: action }))
}

/** A rejection shaped like the API client's, carrying the parsed 409 body. */
function blockedWith(counts: Record<string, unknown>) {
  return Object.assign(new Error('Conflict'), {
    body: {
      detail: {
        detail: 'Deleting this company destroys its entire ledger…',
        invoices: 0,
        lines: 0,
        entries: 0,
        integrations: 1,
        earliest: null,
        latest: null,
        ...counts,
      },
    },
  })
}

describe('CompaniesPanel — deleting a company', () => {
  async function openDeleteDialog(overrides = {}) {
    const props = renderPanel({ canDelete: true, ...overrides })
    await clickRowAction('Acme A/S', 'Delete permanently')
    return { props, dialog: await screen.findByRole('alertdialog') }
  }

  it('offers the action to a system admin', async () => {
    renderPanel({ canDelete: true })
    fireEvent.click(
      screen.getByRole('button', { name: 'Actions for Acme A/S' }),
    )

    expect(
      await screen.findByRole('menuitem', { name: 'Delete permanently' }),
    ).toBeTruthy()
  })

  it('does not render it for anyone else, disabled or otherwise', async () => {
    renderPanel({ canDelete: false })
    fireEvent.click(
      screen.getByRole('button', { name: 'Actions for Acme A/S' }),
    )

    await screen.findByRole('menuitem', { name: 'Deactivate' })
    expect(
      screen.queryByRole('menuitem', { name: 'Delete permanently' }),
    ).toBeNull()
  })

  it('states the consequence and names the reversible alternative', async () => {
    const { dialog } = await openDeleteDialog()

    expect(dialog.textContent).toContain('Delete Acme A/S?')
    expect(dialog.textContent).toContain('cannot be undone')
    expect(dialog.textContent).toMatch(/deactivate/i)
  })

  it('says suppliers are kept, since that is the surprising half', async () => {
    const { dialog } = await openDeleteDialog()

    expect(dialog.textContent).toMatch(/suppliers/i)
  })

  it('keeps the confirm button disabled until the name is typed', async () => {
    const { dialog } = await openDeleteDialog()
    const confirm = within(dialog).getByRole('button', {
      name: 'Delete permanently',
    })

    expect(confirm).toHaveProperty('disabled', true)

    fireEvent.change(
      within(dialog).getByLabelText('Confirm the company name'),
      {
        target: { value: 'Acme A/S' },
      },
    )

    expect(confirm).toHaveProperty('disabled', false)
  })

  it('is not armed by a near miss', async () => {
    const { dialog } = await openDeleteDialog()

    fireEvent.change(
      within(dialog).getByLabelText('Confirm the company name'),
      {
        target: { value: 'Acme' },
      },
    )

    expect(
      within(dialog).getByRole('button', { name: 'Delete permanently' }),
    ).toHaveProperty('disabled', true)
  })

  it('deletes with confirmation once the name matches', async () => {
    const onDelete = vi.fn().mockResolvedValue(undefined)
    const { dialog } = await openDeleteDialog({ onDelete })

    fireEvent.change(
      within(dialog).getByLabelText('Confirm the company name'),
      {
        target: { value: 'Acme A/S' },
      },
    )
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Delete permanently' }),
    )

    await waitFor(() => expect(onDelete).toHaveBeenCalledWith('c1', true))
  })

  it('shows what the server says would be lost, and stays open', async () => {
    const onDelete = vi.fn().mockRejectedValue(
      blockedWith({
        invoices: 203,
        lines: 398,
        entries: 963,
        earliest: '2025-07-01',
        latest: '2026-08-20',
      }),
    )
    const { dialog } = await openDeleteDialog({ onDelete })

    fireEvent.change(
      within(dialog).getByLabelText('Confirm the company name'),
      {
        target: { value: 'Acme A/S' },
      },
    )
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Delete permanently' }),
    )

    await waitFor(() => expect(dialog.textContent).toContain('203'))
    expect(dialog.textContent).toContain('398')
    expect(dialog.textContent).toContain('963')
    expect(dialog.textContent).toContain('2026-08-20')
    expect(screen.getByRole('alertdialog')).toBeTruthy()
  })

  it('shows an ordinary failure inside the dialog', async () => {
    const onDelete = vi.fn().mockRejectedValue(new Error('boom'))
    const { dialog } = await openDeleteDialog({ onDelete })

    fireEvent.change(
      within(dialog).getByLabelText('Confirm the company name'),
      {
        target: { value: 'Acme A/S' },
      },
    )
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Delete permanently' }),
    )

    await waitFor(() => expect(dialog.textContent).toMatch(/boom/i))
    expect(screen.getByRole('alertdialog')).toBeTruthy()
  })

  it('closes without deleting when cancelled', async () => {
    const onDelete = vi.fn()
    const { dialog } = await openDeleteDialog({ onDelete })

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(onDelete).not.toHaveBeenCalled()
  })
})

describe('changedFields', () => {
  it('returns only what actually changed', () => {
    const before = {
      name: 'Acme A/S',
      country_code: 'DK',
      vat_number: 'DK1',
      base_currency: 'DKK',
      spend_tree_id: 'tree1',
    }
    const after = {
      name: 'Acme Group',
      country_code: 'DK',
      vat_number: 'DK1',
      base_currency: 'DKK',
      spend_tree_id: 'tree1',
    }
    expect(changedFields(before, after)).toEqual({ name: 'Acme Group' })
  })

  it('is empty when nothing changed', () => {
    const values = {
      name: 'Acme A/S',
      country_code: 'DK',
      vat_number: 'DK1',
      base_currency: 'DKK',
      spend_tree_id: 'tree1',
    }
    expect(changedFields(values, values)).toEqual({})
  })
})

describe('CompaniesPanel', () => {
  it('lists companies with their details', () => {
    renderPanel()

    expect(screen.getByText('Acme A/S')).toBeTruthy()
    expect(screen.getByText('DK12345678')).toBeTruthy()
    expect(screen.getByText('Active')).toBeTruthy()
  })

  it('invites the first company when there are none', () => {
    renderPanel({ companies: [] })

    expect(screen.getByText('No companies yet')).toBeTruthy()
    expect(
      screen.getByRole('button', { name: 'Add your first company' }),
    ).toBeTruthy()
  })

  it('asks the container to include inactive companies', () => {
    const props = renderPanel()

    fireEvent.click(
      screen.getByRole('switch', { name: 'Show inactive companies' }),
    )

    expect(props.onIncludeInactiveChange).toHaveBeenCalledWith(true)
  })

  it('marks inactive companies when they are shown', () => {
    renderPanel({ companies: [ACME, RETIRED], includeInactive: true })

    expect(screen.getByText('Inactive')).toBeTruthy()
    expect(
      screen.getByRole('button', { name: 'Actions for Old Holdings' }),
    ).toBeTruthy()
  })

  it('creates a company with its ERP connection in one submission', async () => {
    const props = renderPanel({ companies: [] })

    fireEvent.click(
      screen.getByRole('button', { name: 'Add your first company' }),
    )
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'New Co' },
    })
    await chooseCurrency('DKK')
    fireEvent.click(screen.getByRole('button', { name: 'Add company' }))

    await waitFor(() =>
      expect(props.onCreate).toHaveBeenCalledWith({
        name: 'New Co',
        country_code: '',
        vat_number: '',
        base_currency: 'DKK',
        spend_tree_id: '',
        erp_type: 'mock',
        credentials: { base_url: 'http://localhost:8001', api_key: '' },
      }),
    )
    expect(props.onCreate).toHaveBeenCalledTimes(1)
  })

  it('renders the connector and its credential inputs from the catalog', async () => {
    renderPanel({ companies: [] })

    fireEvent.click(
      screen.getByRole('button', { name: 'Add your first company' }),
    )
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    expect(screen.getByText('ERP connection')).toBeTruthy()
    expect(
      (screen.getByRole('radio', { name: /Debug ERP/ }) as HTMLInputElement)
        .checked,
    ).toBe(true)
    expect((screen.getByLabelText('Base URL') as HTMLInputElement).value).toBe(
      'http://localhost:8001',
    )
    expect(
      (screen.getByLabelText('API key (optional)') as HTMLInputElement).type,
    ).toBe('password')
  })

  it('presents each connector as a card built from the catalog', async () => {
    renderPanel({ companies: [], erpTypes: [DEBUG_ERP, BILLY] })

    fireEvent.click(
      screen.getByRole('button', { name: 'Add your first company' }),
    )
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    const group = screen.getByRole('radiogroup', { name: 'ERP system' })
    expect(within(group).getAllByRole('radio')).toHaveLength(2)
    expect(within(group).getByText(BILLY.description!)).toBeTruthy()
    const marks = within(group).getAllByTestId('erp-brand-mark')
    expect(marks).toHaveLength(2)
  })

  it('renders a connector it has never seen exactly like the others', async () => {
    const unknown: ErpTypeRead = {
      erp_type: 'visma',
      label: 'Visma.net',
      credential_fields: [],
    }
    renderPanel({ companies: [], erpTypes: [DEBUG_ERP, unknown] })

    fireEvent.click(
      screen.getByRole('button', { name: 'Add your first company' }),
    )
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    const card = screen.getByTestId('erp-type-visma')
    expect(within(card).getByRole('radio')).toBeTruthy()
    expect(within(card).getByTestId('erp-brand-mark').dataset.variant).toBe(
      'letter',
    )
  })

  it('reseeds the credential inputs when another connector is chosen', async () => {
    renderPanel({ companies: [], erpTypes: [DEBUG_ERP, BILLY] })

    fireEvent.click(
      screen.getByRole('button', { name: 'Add your first company' }),
    )
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.click(screen.getByRole('radio', { name: /Debug ERP/ }))
    expect((screen.getByLabelText('Base URL') as HTMLInputElement).value).toBe(
      'http://localhost:8001',
    )

    fireEvent.click(screen.getByRole('radio', { name: /Billy/ }))
    await waitFor(() =>
      expect(screen.getByLabelText('Access token')).toBeTruthy(),
    )
    expect(screen.queryByLabelText('Base URL')).toBeNull()
    expect(
      (screen.getByLabelText('Access token') as HTMLInputElement).type,
    ).toBe('password')
  })

  it('submits the company and the chosen connector as one request', async () => {
    const props = renderPanel({ companies: [], erpTypes: [DEBUG_ERP, BILLY] })

    fireEvent.click(
      screen.getByRole('button', { name: 'Add your first company' }),
    )
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Nordwind ApS' },
    })
    await chooseCurrency('DKK')
    fireEvent.click(screen.getByRole('radio', { name: /Billy/ }))
    await waitFor(() =>
      expect(screen.getByLabelText('Access token')).toBeTruthy(),
    )
    fireEvent.change(screen.getByLabelText('Access token'), {
      target: { value: 'tok-1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add company' }))

    await waitFor(() =>
      expect(props.onCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Nordwind ApS',
          erp_type: 'billy',
          credentials: { access_token: 'tok-1' },
        }),
      ),
    )
  })

  it('blocks submission when a required credential is empty', async () => {
    const props = renderPanel({ companies: [] })

    fireEvent.click(
      screen.getByRole('button', { name: 'Add your first company' }),
    )
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'New Co' },
    })
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: '   ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add company' }))

    await waitFor(() =>
      expect(screen.getByText('Enter the base url.')).toBeTruthy(),
    )
    expect(props.onCreate).not.toHaveBeenCalled()
  })

  it('warns when no ERP system is available to connect', async () => {
    renderPanel({ companies: [], erpTypes: [] })

    fireEvent.click(
      screen.getByRole('button', { name: 'Add your first company' }),
    )

    await waitFor(() =>
      expect(screen.getByText(/No ERP systems are available/)).toBeTruthy(),
    )
  })

  it('sends only changed company fields when the connection is untouched', async () => {
    const props = renderPanel()

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Acme Group' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(props.onUpdate).toHaveBeenCalledWith('c1', { name: 'Acme Group' }),
    )
    expect(props.onUpdateIntegration).not.toHaveBeenCalled()
    expect(props.onConnectIntegration).not.toHaveBeenCalled()
  })

  it('reports stored credentials without showing or prefilling them', async () => {
    renderPanel()

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    expect(screen.getByText(/Credentials are set/)).toBeTruthy()
    expect(screen.queryByLabelText('Base URL')).toBeNull()
    expect(screen.queryByLabelText('API key (optional)')).toBeNull()
    expect(screen.getByText(/Debug ERP/)).toBeTruthy()
    expect(screen.queryByRole('combobox', { name: 'ERP system' })).toBeNull()
  })

  it('renames the integration label without touching credentials', async () => {
    const props = renderPanel()

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() =>
      expect(screen.getByLabelText('Connection label (optional)')).toBeTruthy(),
    )

    fireEvent.change(screen.getByLabelText('Connection label (optional)'), {
      target: { value: 'Production' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(props.onUpdateIntegration).toHaveBeenCalledWith('i1', {
        label: 'Production',
      }),
    )
    expect(props.onUpdate).not.toHaveBeenCalled()
  })

  it('replaces every credential when replacement is chosen', async () => {
    const props = renderPanel()

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.click(screen.getByRole('switch', { name: 'Replace credentials' }))
    await waitFor(() => expect(screen.getByLabelText('Base URL')).toBeTruthy())
    expect(
      screen.getByText(/replacing them means entering every field again/),
    ).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'http://erp.local' },
    })
    fireEvent.change(screen.getByLabelText('API key (optional)'), {
      target: { value: 'k' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(props.onUpdateIntegration).toHaveBeenCalledWith('i1', {
        credentials: { base_url: 'http://erp.local', api_key: 'k' },
      }),
    )
  })

  it('shows the connector grid when editing, not a caption', async () => {
    renderPanel({ erpTypes: [DEBUG_ERP, BILLY] })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    expect(screen.getByRole('radiogroup', { name: 'ERP system' })).toBeTruthy()
    const chosen = screen
      .getByTestId('erp-type-mock')
      .querySelector('input') as HTMLInputElement
    expect(chosen.checked).toBe(true)
  })

  it('names the connected system when it is missing from the catalog', async () => {
    renderPanel({ erpTypes: [BILLY] })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    const grid = screen.getByRole('radiogroup', { name: 'ERP system' })
    const radios = within(grid).getAllByRole('radio') as HTMLInputElement[]
    expect(radios.some((radio) => radio.checked)).toBe(false)
    expect(screen.getByText(/mock/)).toBeTruthy()
  })

  it('reveals the new connector fields when a different system is picked', async () => {
    renderPanel({ erpTypes: [DEBUG_ERP, BILLY] })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.click(screen.getByTestId('erp-type-billy'))

    await waitFor(() =>
      expect(screen.getByLabelText('Access token')).toBeTruthy(),
    )
    expect(
      screen.queryByRole('switch', { name: 'Replace credentials' }),
    ).toBeNull()
  })

  it('restores the replace-credentials form when the current system is reselected', async () => {
    renderPanel({ erpTypes: [DEBUG_ERP, BILLY] })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.click(screen.getByTestId('erp-type-billy'))
    await waitFor(() =>
      expect(screen.getByLabelText('Access token')).toBeTruthy(),
    )
    fireEvent.click(screen.getByTestId('erp-type-mock'))

    await waitFor(() =>
      expect(
        screen.getByRole('switch', { name: 'Replace credentials' }),
      ).toBeTruthy(),
    )
    expect(screen.queryByLabelText('Access token')).toBeNull()
  })

  it('connects an ERP to a company that has none', async () => {
    const props = renderPanel({ integrations: [] })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() =>
      expect(screen.getByText(/not connected to an ERP/)).toBeTruthy(),
    )

    expect(
      (screen.getByRole('radio', { name: /Debug ERP/ }) as HTMLInputElement)
        .checked,
    ).toBe(false)
    fireEvent.click(screen.getByRole('radio', { name: /Debug ERP/ }))
    await waitFor(() => expect(screen.getByLabelText('Base URL')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(props.onConnectIntegration).toHaveBeenCalledWith('c1', {
        erp_type: 'mock',
        label: '',
        credentials: { base_url: 'http://localhost:8001' },
      }),
    )
  })

  it('leaves an unconnected company alone when the connection is skipped', async () => {
    const props = renderPanel({ integrations: [] })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Acme Group' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(props.onUpdate).toHaveBeenCalledWith('c1', { name: 'Acme Group' }),
    )
    expect(props.onConnectIntegration).not.toHaveBeenCalled()
  })

  it('says when a company has other integrations rather than hiding them', async () => {
    renderPanel({
      integrations: [
        INTEGRATION,
        { ...INTEGRATION, id: 'i2', label: 'Secondary' },
        { ...INTEGRATION, id: 'i3', label: 'Third' },
      ],
    })

    await clickRowAction('Acme A/S', 'Edit')

    await waitFor(() =>
      expect(screen.getByText(/2 other integrations/)).toBeTruthy(),
    )
  })

  it('surfaces a rejected integration update instead of reporting success', async () => {
    const onUpdateIntegration = vi
      .fn()
      .mockRejectedValue(new Error('Invalid credentials'))
    renderPanel({ onUpdateIntegration })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() =>
      expect(screen.getByLabelText('Connection label (optional)')).toBeTruthy(),
    )

    fireEvent.change(screen.getByLabelText('Connection label (optional)'), {
      target: { value: 'Production' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(screen.getAllByText('Invalid credentials').length).toBeGreaterThan(
        0,
      ),
    )
    expect(screen.queryByText('Company updated')).toBeNull()
  })

  it('deactivates only after confirmation, and never offers delete', async () => {
    const props = renderPanel()

    await clickRowAction('Acme A/S', 'Deactivate')
    expect(props.onSetActive).not.toHaveBeenCalled()

    const dialog = await screen.findByRole('alertdialog')
    expect(dialog.textContent).toContain('Deactivate Acme A/S?')
    expect(dialog.textContent).toMatch(/invoices and ledger entries are kept/)

    fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate' }))
    await waitFor(() =>
      expect(props.onSetActive).toHaveBeenCalledWith('c1', false),
    )

    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull()
    expect(screen.queryByRole('menuitem', { name: 'Delete' })).toBeNull()
  })

  it('abandons a deactivation on cancel', async () => {
    const props = renderPanel()

    await clickRowAction('Acme A/S', 'Deactivate')
    const dialog = await screen.findByRole('alertdialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(props.onSetActive).not.toHaveBeenCalled()
  })

  it('reactivates without confirmation', async () => {
    const props = renderPanel({ companies: [RETIRED], includeInactive: true })

    await clickRowAction('Old Holdings', 'Reactivate')

    await waitFor(() =>
      expect(props.onSetActive).toHaveBeenCalledWith('c2', true),
    )
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })

  it('is read-only for a viewer', () => {
    renderPanel({ canManage: false })

    expect(screen.queryByRole('button', { name: 'Add company' })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Actions for/ })).toBeNull()
    expect(screen.getByText(/admin or moderator role/)).toBeTruthy()
    expect(screen.getByText('Acme A/S')).toBeTruthy()
  })

  it('surfaces a server rejection of a deactivate', async () => {
    const onSetActive = vi
      .fn()
      .mockRejectedValue(new Error('Insufficient permissions'))
    renderPanel({ onSetActive })

    await clickRowAction('Acme A/S', 'Deactivate')
    const dialog = await screen.findByRole('alertdialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate' }))

    await waitFor(() =>
      expect(screen.getByText('Insufficient permissions')).toBeTruthy(),
    )
    expect(screen.getByText('Active')).toBeTruthy()
  })
})

describe('CompaniesPanel — manage accounts', () => {
  it('navigates to the company whose menu was opened', async () => {
    const onManageAccounts = vi.fn()
    renderPanel({ onManageAccounts })

    await clickRowAction('Acme A/S', 'Manage accounts')

    expect(onManageAccounts).toHaveBeenCalledWith('c1')
  })

  it('is disabled for a company with no ERP connection', async () => {
    renderPanel({ integrations: [], onManageAccounts: vi.fn() })

    fireEvent.click(
      screen.getByRole('button', { name: 'Actions for Acme A/S' }),
    )
    const item = await screen.findByRole('menuitem', {
      name: 'Manage accounts',
    })

    expect(item.getAttribute('aria-disabled')).toBe('true')
  })
})

describe('CompaniesPanel — reporting currency', () => {
  it('shows each company’s reporting currency in the list', () => {
    renderPanel({ companies: [ACME, RETIRED], includeInactive: true })

    expect(screen.getByText('DKK')).toBeTruthy()
    expect(screen.getByText('EUR')).toBeTruthy()
  })

  it('will not create a company without one', async () => {
    const props = renderPanel({ companies: [] })

    fireEvent.click(
      screen.getByRole('button', { name: 'Add your first company' }),
    )
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'New Co' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add company' }))

    expect(await screen.findByText('Choose a reporting currency.')).toBeTruthy()
    expect(props.onCreate).not.toHaveBeenCalled()
  })

  it('pre-selects the currency the chosen country implies', async () => {
    renderPanel({ companies: [] })

    fireEvent.click(
      screen.getByRole('button', { name: 'Add your first company' }),
    )
    await waitFor(() => expect(screen.getByLabelText('Country')).toBeTruthy())
    await chooseCountry('SE')

    const currency = screen.getByRole('combobox', {
      name: 'Reporting currency',
    }) as HTMLInputElement
    await waitFor(() => expect(currency.value).toContain('SEK'))
  })

  it('keeps a currency the user chose over the country’s', async () => {
    renderPanel({ companies: [] })

    fireEvent.click(
      screen.getByRole('button', { name: 'Add your first company' }),
    )
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())
    await chooseCurrency('EUR')
    await chooseCountry('DK')

    const currency = screen.getByRole('combobox', {
      name: 'Reporting currency',
    }) as HTMLInputElement
    await waitFor(() => expect(currency.value).toContain('EUR'))
  })

  it('is read-only without management rights', () => {
    renderPanel({ canManage: false })

    expect(
      screen.queryByRole('button', { name: 'Actions for Acme A/S' }),
    ).toBeNull()
    expect(screen.getByText('DKK')).toBeTruthy()
  })
})

describe('CompaniesPanel — recompute', () => {
  it('offers a recompute after the reporting currency changes', async () => {
    const props = renderPanel()

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())
    await chooseCurrency('EUR')
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(props.onUpdate).toHaveBeenCalledWith('c1', {
        base_currency: 'EUR',
      }),
    )
    expect(await screen.findByText(/Recompute Acme A\/S/)).toBeTruthy()
    expect(props.onRecomputeFx).not.toHaveBeenCalled()
  })

  it('reports what the recompute did', async () => {
    const props = renderPanel()

    await clickRowAction('Acme A/S', 'Recompute currency figures')
    fireEvent.click(await screen.findByRole('button', { name: 'Recompute' }))

    await waitFor(() => expect(props.onRecomputeFx).toHaveBeenCalledWith('c1'))
    expect(await screen.findByText(/12 converted/)).toBeTruthy()
    expect(screen.getByText(/1 left unconverted/)).toBeTruthy()
  })

  it('leaves the currency change in place when the recompute is declined', async () => {
    const props = renderPanel()

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())
    await chooseCurrency('EUR')
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Not now' }))

    expect(props.onUpdate).toHaveBeenCalledWith('c1', { base_currency: 'EUR' })
    expect(props.onRecomputeFx).not.toHaveBeenCalled()
    await clickRowAction('Acme A/S', 'Recompute currency figures')
    expect(
      await screen.findByRole('button', { name: 'Recompute' }),
    ).toBeTruthy()
  })

  it('does not offer a recompute when the container provides none', async () => {
    renderPanel({ onRecomputeFx: undefined })

    fireEvent.click(
      screen.getByRole('button', { name: 'Actions for Acme A/S' }),
    )
    await waitFor(() =>
      expect(screen.getByRole('menuitem', { name: 'Edit' })).toBeTruthy(),
    )
    expect(
      screen.queryByRole('menuitem', { name: 'Recompute currency figures' }),
    ).toBeNull()
  })
})

describe('CompaniesPanel — switching ERPs', () => {
  it('replaces the integration instead of patching it when the system changed', async () => {
    const onReplaceIntegration = vi.fn().mockResolvedValue({ id: 'new-1' })
    const onUpdateIntegration = vi.fn()
    renderPanel({
      erpTypes: [DEBUG_ERP, BILLY],
      onReplaceIntegration,
      onUpdateIntegration,
    })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.click(screen.getByTestId('erp-type-billy'))
    await waitFor(() =>
      expect(screen.getByLabelText('Access token')).toBeTruthy(),
    )
    fireEvent.change(screen.getByLabelText('Access token'), {
      target: { value: 'tok_live' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(onReplaceIntegration).toHaveBeenCalledWith('i1', {
        erp_type: 'billy',
        label: 'Main',
        credentials: { access_token: 'tok_live' },
      }),
    )
    expect(onUpdateIntegration).not.toHaveBeenCalled()
  })

  it('confirms a replacement the API says would double spend', async () => {
    const blocked = Object.assign(new Error('conflict'), {
      status: 409,
      body: {
        detail: {
          detail: 'This ERP has already posted to the ledger.',
          invoices: 25,
          entries: 989,
          earliest: '2026-01-05',
          latest: '2026-03-20',
        },
      },
    })
    const onReplaceIntegration = vi
      .fn()
      .mockRejectedValueOnce(blocked)
      .mockResolvedValueOnce({ id: 'new-1' })
    renderPanel({ erpTypes: [DEBUG_ERP, BILLY], onReplaceIntegration })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.click(screen.getByTestId('erp-type-billy'))
    await waitFor(() =>
      expect(screen.getByLabelText('Access token')).toBeTruthy(),
    )
    fireEvent.change(screen.getByLabelText('Access token'), {
      target: { value: 'tok_live' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText(/989/)).toBeTruthy()
    expect(screen.getByText(/25 invoices/i)).toBeTruthy()
    expect(screen.getByLabelText('Name')).toBeTruthy()
    expect(screen.queryByText('Company updated')).toBeNull()
    expect(screen.queryByText('Couldn’t save your changes')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /switch anyway/i }))

    await waitFor(() =>
      expect(onReplaceIntegration).toHaveBeenLastCalledWith(
        'i1',
        expect.objectContaining({ confirm: true }),
      ),
    )
    await waitFor(() => expect(screen.queryByLabelText('Name')).toBeNull())
  })

  it('surfaces a failed retry instead of dropping it silently', async () => {
    const blocked = Object.assign(new Error('conflict'), {
      status: 409,
      body: {
        detail: {
          detail: 'This ERP has already posted to the ledger.',
          invoices: 25,
          entries: 989,
          earliest: '2026-01-05',
          latest: '2026-03-20',
        },
      },
    })
    const onReplaceIntegration = vi
      .fn()
      .mockRejectedValueOnce(blocked)
      .mockRejectedValueOnce(new Error('Ledger service unavailable'))
    renderPanel({ erpTypes: [DEBUG_ERP, BILLY], onReplaceIntegration })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.click(screen.getByTestId('erp-type-billy'))
    await waitFor(() =>
      expect(screen.getByLabelText('Access token')).toBeTruthy(),
    )
    fireEvent.change(screen.getByLabelText('Access token'), {
      target: { value: 'tok_live' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText(/989/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /switch anyway/i }))

    expect(await screen.findByText('Ledger service unavailable')).toBeTruthy()
    expect(screen.getByRole('button', { name: /switch anyway/i })).toBeTruthy()
    expect(screen.queryByText('Company updated')).toBeNull()
  })

  it('still patches when the selected connector is the one already connected', async () => {
    const onReplaceIntegration = vi.fn()
    const props = renderPanel({
      erpTypes: [DEBUG_ERP, BILLY],
      onReplaceIntegration,
    })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() =>
      expect(screen.getByLabelText('Connection label (optional)')).toBeTruthy(),
    )

    fireEvent.change(screen.getByLabelText('Connection label (optional)'), {
      target: { value: 'Production' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(props.onUpdateIntegration).toHaveBeenCalledWith('i1', {
        label: 'Production',
      }),
    )
    expect(onReplaceIntegration).not.toHaveBeenCalled()
  })

  it('reports a non-409 replacement failure instead of opening the confirm dialog', async () => {
    const onReplaceIntegration = vi
      .fn()
      .mockRejectedValue(new Error('Invalid credentials'))
    renderPanel({ erpTypes: [DEBUG_ERP, BILLY], onReplaceIntegration })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.click(screen.getByTestId('erp-type-billy'))
    await waitFor(() =>
      expect(screen.getByLabelText('Access token')).toBeTruthy(),
    )
    fireEvent.change(screen.getByLabelText('Access token'), {
      target: { value: 'tok_live' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(screen.getAllByText('Invalid credentials').length).toBeGreaterThan(
        0,
      ),
    )
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(screen.queryByText('Company updated')).toBeNull()
  })

  it('disables the confirm dialog while a switch is in flight, so a double-click cannot double the ledger', async () => {
    const blocked = Object.assign(new Error('conflict'), {
      status: 409,
      body: {
        detail: {
          detail: 'This ERP has already posted to the ledger.',
          invoices: 25,
          entries: 989,
          earliest: '2026-01-05',
          latest: '2026-03-20',
        },
      },
    })
    let resolveConfirm: (value: unknown) => void = () => {}
    const confirmPromise = new Promise((resolve) => {
      resolveConfirm = resolve
    })
    const onReplaceIntegration = vi
      .fn()
      .mockRejectedValueOnce(blocked)
      .mockReturnValueOnce(confirmPromise)
    renderPanel({ erpTypes: [DEBUG_ERP, BILLY], onReplaceIntegration })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.click(screen.getByTestId('erp-type-billy'))
    await waitFor(() =>
      expect(screen.getByLabelText('Access token')).toBeTruthy(),
    )
    fireEvent.change(screen.getByLabelText('Access token'), {
      target: { value: 'tok_live' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText(/989/)).toBeTruthy()

    const cancelButton = screen.getByRole('button', { name: 'Cancel' })
    fireEvent.click(screen.getByRole('button', { name: /switch anyway/i }))

    const switchingButton = await screen.findByRole('button', {
      name: /switching/i,
    })
    expect((switchingButton as HTMLButtonElement).disabled).toBe(true)
    expect((cancelButton as HTMLButtonElement).disabled).toBe(true)
    expect(onReplaceIntegration).toHaveBeenCalledTimes(2)

    fireEvent.click(switchingButton)
    expect(onReplaceIntegration).toHaveBeenCalledTimes(2)

    resolveConfirm({ id: 'new-1' })
    await waitFor(() => expect(screen.queryByLabelText('Name')).toBeNull())
  })

  it('toasts success after a confirmed switch, since the dialog closing alone is a weak signal', async () => {
    const blocked = Object.assign(new Error('conflict'), {
      status: 409,
      body: {
        detail: {
          detail: 'This ERP has already posted to the ledger.',
          invoices: 25,
          entries: 989,
          earliest: '2026-01-05',
          latest: '2026-03-20',
        },
      },
    })
    const onReplaceIntegration = vi
      .fn()
      .mockRejectedValueOnce(blocked)
      .mockResolvedValueOnce({ id: 'new-1' })
    renderPanel({ erpTypes: [DEBUG_ERP, BILLY], onReplaceIntegration })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.click(screen.getByTestId('erp-type-billy'))
    await waitFor(() =>
      expect(screen.getByLabelText('Access token')).toBeTruthy(),
    )
    fireEvent.change(screen.getByLabelText('Access token'), {
      target: { value: 'tok_live' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText(/989/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /switch anyway/i }))

    await waitFor(() => expect(screen.queryByLabelText('Name')).toBeNull())
    expect(await screen.findByText(/switch/i)).toBeTruthy()
  })
})

describe('CompaniesPanel — recategorize failed lines', () => {
  it('offers the action to a management user', async () => {
    renderPanel()

    fireEvent.click(
      screen.getByRole('button', { name: 'Actions for Acme A/S' }),
    )

    expect(
      await screen.findByRole('menuitem', {
        name: 'Recategorize failed lines',
      }),
    ).toBeTruthy()
  })

  it('does not offer it without management rights', () => {
    renderPanel({ canManage: false })

    expect(
      screen.queryByRole('button', { name: 'Actions for Acme A/S' }),
    ).toBeNull()
  })

  it('does not offer it when the container provides no handler', async () => {
    renderPanel({ onRecategorize: undefined })

    fireEvent.click(
      screen.getByRole('button', { name: 'Actions for Acme A/S' }),
    )
    await screen.findByRole('menuitem', { name: 'Edit' })

    expect(
      screen.queryByRole('menuitem', { name: 'Recategorize failed lines' }),
    ).toBeNull()
  })

  it('says the lines are queued, not categorized, before running', async () => {
    const props = renderPanel()

    await clickRowAction('Acme A/S', 'Recategorize failed lines')

    expect(
      await screen.findByText(/categorized on the next sync run/i),
    ).toBeTruthy()
    expect(screen.getByText(/nothing is categorized right now/i)).toBeTruthy()
    expect(props.onRecategorize).not.toHaveBeenCalled()
  })

  it('reports how many lines were queued', async () => {
    const props = renderPanel()

    await clickRowAction('Acme A/S', 'Recategorize failed lines')
    fireEvent.click(
      await screen.findByRole('button', { name: 'Queue for recategorization' }),
    )

    await waitFor(() => expect(props.onRecategorize).toHaveBeenCalledWith('c1'))
    expect(await screen.findByText(/28/)).toBeTruthy()
  })

  it('says plainly when there was nothing to queue', async () => {
    const props = renderPanel({
      onRecategorize: vi
        .fn()
        .mockResolvedValue({ company_id: 'c1', queued: 0 }),
    })

    await clickRowAction('Acme A/S', 'Recategorize failed lines')
    fireEvent.click(
      await screen.findByRole('button', { name: 'Queue for recategorization' }),
    )

    await waitFor(() => expect(props.onRecategorize).toHaveBeenCalled())
    expect(await screen.findByText(/no failed lines/i)).toBeTruthy()
  })

  it('does not report success when the request fails', async () => {
    renderPanel({
      onRecategorize: vi.fn().mockRejectedValue(new Error('boom')),
    })

    await clickRowAction('Acme A/S', 'Recategorize failed lines')
    fireEvent.click(
      await screen.findByRole('button', { name: 'Queue for recategorization' }),
    )

    expect(await screen.findByText(/boom/i)).toBeTruthy()
    expect(screen.queryByText(/queued for the categorizer/i)).toBeNull()
  })
})
