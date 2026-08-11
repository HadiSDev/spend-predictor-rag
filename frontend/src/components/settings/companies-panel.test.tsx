import { describe, expect, it, vi } from 'vitest'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { ToastProvider } from '#/components/ui'
import type { CompanyRead, ErpIntegrationRead, ErpTypeRead } from '#/lib/types'
import { CompaniesPanel, changedFields } from './companies-panel'
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
    onRecomputeFx: vi.fn().mockResolvedValue({
      company_id: 'c1',
      base_currency: 'EUR',
      converted: 12,
      unconverted: 1,
      unchanged: 3,
    }),
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

/** Row actions live behind a per-row menu, so reaching one is two steps. */
async function clickRowAction(companyName: string, action: string) {
  fireEvent.click(
    screen.getByRole('button', { name: `Actions for ${companyName}` }),
  )
  fireEvent.click(await screen.findByRole('menuitem', { name: action }))
}

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
        // The default-tree option: empty here, normalized to null by the route
        // so the server materializes the organization's template copy.
        spend_tree_id: '',
        // The sole connector is preselected and its declared default filled in.
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
    // One option, so it is chosen rather than presented as a decision.
    expect(
      (screen.getByRole('radio', { name: /Debug ERP/ }) as HTMLInputElement)
        .checked,
    ).toBe(true)
    expect((screen.getByLabelText('Base URL') as HTMLInputElement).value).toBe(
      'http://localhost:8001',
    )
    // Secrets are masked; optional fields say so.
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
    // The catalog's own description, never text invented here.
    expect(within(group).getByText(BILLY.description!)).toBeTruthy()
    // Billy has vendored artwork; the debug connector's card still renders.
    const marks = within(group).getAllByTestId('erp-brand-mark')
    expect(marks).toHaveLength(2)
  })

  it('renders a connector it has never seen exactly like the others', async () => {
    // The front-end knows no connector by name, so one registered later needs
    // no change here — it just arrives in the catalog.
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
    // No artwork and no description, and it still reads as a card.
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
    // The previous connector's fields are gone, not left behind to be submitted.
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
    // Nothing about the integration changed, so it is not written to at all.
    expect(props.onUpdateIntegration).not.toHaveBeenCalled()
    expect(props.onConnectIntegration).not.toHaveBeenCalled()
  })

  it('reports stored credentials without showing or prefilling them', async () => {
    renderPanel()

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    expect(screen.getByText(/Credentials are set/)).toBeTruthy()
    // Not shown, and no input is standing by prefilled.
    expect(screen.queryByLabelText('Base URL')).toBeNull()
    expect(screen.queryByLabelText('API key (optional)')).toBeNull()
    // The connector is stated but cannot be swapped here.
    expect(screen.getByText(/Debug ERP/)).toBeTruthy()
    // The currency picker is a combobox too, so this asks specifically about
    // the connector one.
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
      // No `credentials` key at all — the stored secret is left alone.
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

  it('reveals the new connector fields when a different system is picked', async () => {
    renderPanel({ erpTypes: [DEBUG_ERP, BILLY] })

    await clickRowAction('Acme A/S', 'Edit')
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeTruthy())

    fireEvent.click(screen.getByTestId('erp-type-billy'))

    await waitFor(() =>
      expect(screen.getByLabelText('Access token')).toBeTruthy(),
    )
    // Nothing is stored for a connector not yet connected, so there is
    // nothing to offer replacing.
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

    // Optional here, so nothing is preselected — connecting is a deliberate act.
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

    // Reported (inline and in the toast); never as a success.
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
    // Choosing it from the menu only asks — it does not act.
    expect(props.onSetActive).not.toHaveBeenCalled()

    // The dialog names the company and states what deactivation costs.
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog.textContent).toContain('Deactivate Acme A/S?')
    expect(dialog.textContent).toMatch(/invoices and ledger entries are kept/)

    fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate' }))
    await waitFor(() =>
      expect(props.onSetActive).toHaveBeenCalledWith('c1', false),
    )

    // Soft-deactivation only — deleting is never on offer, menu or dialog.
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

    // Restoring is not destructive, so it acts straight from the menu.
    await clickRowAction('Old Holdings', 'Reactivate')

    await waitFor(() =>
      expect(props.onSetActive).toHaveBeenCalledWith('c2', true),
    )
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })

  it('is read-only for a viewer', () => {
    renderPanel({ canManage: false })

    expect(screen.queryByRole('button', { name: 'Add company' })).toBeNull()
    // No row menu at all, so none of its actions are reachable.
    expect(screen.queryByRole('button', { name: /^Actions for/ })).toBeNull()
    expect(screen.getByText(/admin or moderator role/)).toBeTruthy()
    // The data itself is still there to read.
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
    // The row is unchanged — nothing claims the change succeeded.
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
    // Nothing to manage: the chart of accounts belongs to the integration.
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

    // A Danish company reporting in EUR is ordinary — the guess must not win.
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
    // The change is saved, and the consequence is explained straight away.
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
    // Still reachable later, from the row menu.
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

    fireEvent.click(screen.getByRole('button', { name: /switch anyway/i }))

    await waitFor(() =>
      expect(onReplaceIntegration).toHaveBeenLastCalledWith(
        'i1',
        expect.objectContaining({ confirm: true }),
      ),
    )
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

    // Reported as a form failure — never as the counts dialog, since there
    // are no counts to show.
    await waitFor(() =>
      expect(screen.getAllByText('Invalid credentials').length).toBeGreaterThan(
        0,
      ),
    )
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(screen.queryByText('Company updated')).toBeNull()
  })
})
