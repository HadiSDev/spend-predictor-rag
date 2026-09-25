import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { SpendTreesPanel } from './spend-trees-panel'
import type { SpendTreesPanelProps } from './spend-trees-panel'
import type { SpendTreeRead } from '#/lib/api/types'

function tree(overrides: Partial<SpendTreeRead> = {}): SpendTreeRead {
  return {
    id: 'tree1',
    name: 'Default spend tree',
    max_depth: 3,
    source: 'default_template',
    template_version: '1',
    archived_at: null,
    created_at: '2026-07-01T00:00:00Z',
    node_count: 24,
    company_ids: ['c1'],
    company_names: ['Acme A/S'],
    ...overrides,
  }
}

function renderPanel(overrides: Partial<SpendTreesPanelProps> = {}) {
  const props: SpendTreesPanelProps = {
    trees: [tree()],
    canManage: true,
    onCreate: vi.fn().mockResolvedValue(tree({ id: 'new', source: 'custom' })),
    onUseDefault: vi.fn().mockResolvedValue(undefined),
    onImport: vi.fn().mockResolvedValue({
      created: 4,
      updated: 0,
      removed: 0,
      stale_lines: 0,
    }),
    onOpenTree: vi.fn(),
    ...overrides,
  }
  render(<SpendTreesPanel {...props} />)
  return props
}

describe('SpendTreesPanel', () => {
  it('lists each tree with what a manager chooses between them on', () => {
    renderPanel()
    expect(screen.getByText('Default spend tree')).toBeTruthy()
    expect(
      screen.getByText(/3 levels · 24 categories · Used by Acme A\/S/),
    ).toBeTruthy()
    expect(screen.getByText(/^Default$/)).toBeTruthy()
  })

  it('says when a tree is assigned to nothing', () => {
    renderPanel({ trees: [tree({ company_names: [], company_ids: [] })] })
    expect(screen.getByText(/not assigned to a company/i)).toBeTruthy()
  })

  it('withholds every mutating control from a read-only member', () => {
    renderPanel({ canManage: false })
    const create = screen.getByRole('button', { name: /new tree/i })
    expect(create).toHaveProperty('disabled', true)
    expect(create.getAttribute('title')).toMatch(/admin or moderator/i)
  })

  it('shows the loading, empty, and error states distinctly', () => {
    const { unmount } = render(
      <SpendTreesPanel
        trees={[]}
        error
        canManage
        onCreate={vi.fn()}
        onImport={vi.fn()}
        onOpenTree={vi.fn()}
      />,
    )
    expect(screen.getByText(/couldn’t load the spend trees/i)).toBeTruthy()
    unmount()

    renderPanel({ trees: [] })
    expect(screen.getByText(/no spend trees yet/i)).toBeTruthy()
  })

  it('opens a tree for editing', () => {
    const props = renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /default spend tree/i }))
    expect(props.onOpenTree).toHaveBeenCalledWith('tree1')
  })

  it('clones an existing tree', async () => {
    const props = renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /new tree/i }))

    fireEvent.change(await screen.findByLabelText('Name'), {
      target: { value: 'Our tree' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create tree/i }))

    await waitFor(() =>
      expect(props.onCreate).toHaveBeenCalledWith({
        name: 'Our tree',
        max_depth: 3,
        source_tree_id: 'tree1',
      }),
    )
  })

  it('creates an empty tree with no source', async () => {
    const props = renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /new tree/i }))

    fireEvent.change(await screen.findByLabelText('Name'), {
      target: { value: 'Blank' },
    })
    fireEvent.click(screen.getByRole('radio', { name: /start empty/i }))
    fireEvent.click(screen.getByRole('button', { name: /create tree/i }))

    await waitFor(() =>
      expect(props.onCreate).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Blank', source_tree_id: null }),
      ),
    )
  })

  it('shows the row count before an import is applied', async () => {
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /new tree/i }))
    fireEvent.click(await screen.findByRole('radio', { name: /import a csv/i }))

    fireEvent.change(screen.getByLabelText('CSV'), {
      target: {
        value: 'level_1,level_2\nIndirect,Technology\nIndirect,Logistics\n',
      },
    })
    expect(screen.getByText(/3 lines to import/i)).toBeTruthy()
  })

  it('names the offending rows when an import is rejected', async () => {
    const onImport = vi.fn().mockRejectedValue({
      detail: {
        message: '1 row(s) could not be imported; nothing was changed.',
        errors: [{ line: 4, message: 'This row skips a level.' }],
      },
    })
    renderPanel({ onImport })

    fireEvent.click(screen.getByRole('button', { name: /new tree/i }))
    fireEvent.change(await screen.findByLabelText('Name'), {
      target: { value: 'Imported' },
    })
    fireEvent.click(screen.getByRole('radio', { name: /import a csv/i }))
    fireEvent.change(screen.getByLabelText('CSV'), {
      target: { value: 'level_1,level_3\nIndirect,Orphan\n' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create tree/i }))

    expect(await screen.findByText(/Line 4:/)).toBeTruthy()
    expect(screen.getByText(/this row skips a level/i)).toBeTruthy()
  })
})

describe('SpendTreesPanel — the default tree', () => {
  it('offers to add the default when the organization has none', async () => {
    const props = renderPanel({
      trees: [tree({ source: 'custom', name: 'Test' })],
    })
    fireEvent.click(
      screen.getByRole('button', { name: /add the default tree/i }),
    )
    await waitFor(() => expect(props.onUseDefault).toHaveBeenCalled())
  })

  it('offers it from the empty state too', async () => {
    const props = renderPanel({ trees: [] })
    expect(
      screen.getByText(
        /companies created before spend trees existed have none/i,
      ),
    ).toBeTruthy()
    fireEvent.click(
      screen.getByRole('button', { name: /add the default tree/i }),
    )
    await waitFor(() => expect(props.onUseDefault).toHaveBeenCalled())
  })

  it('stops offering it once the copy exists', () => {
    renderPanel({ trees: [tree()] })
    expect(
      screen.queryByRole('button', { name: /add the default tree/i }),
    ).toBeNull()
  })

  it('withholds it from a read-only member', () => {
    renderPanel({ trees: [], canManage: false })
    expect(
      screen.getByRole('button', { name: /add the default tree/i }),
    ).toHaveProperty('disabled', true)
  })
})

describe('SpendTreesPanel — deleting a tree', () => {
  it('deletes an unused tree from the row menu', async () => {
    const onDelete = vi.fn().mockResolvedValue({ stale_lines: 0 })
    renderPanel({ onDelete })

    fireEvent.click(
      screen.getByRole('button', { name: /actions for default spend tree/i }),
    )
    fireEvent.click(await screen.findByRole('menuitem', { name: /delete/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }))

    await waitFor(() =>
      expect(onDelete).toHaveBeenCalledWith({ id: 'tree1', confirm: false }),
    )
  })

  it('surfaces a refusal and lets a line-orphaning delete be confirmed', async () => {
    const onDelete = vi
      .fn()
      .mockRejectedValueOnce({
        detail:
          '3 invoice line(s) are categorized against this tree. They keep their ' +
          'categories on record but will need reviewing.',
      })
      .mockResolvedValueOnce({ stale_lines: 3 })
    renderPanel({ onDelete })

    fireEvent.click(
      screen.getByRole('button', { name: /actions for default spend tree/i }),
    )
    fireEvent.click(await screen.findByRole('menuitem', { name: /delete/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }))

    expect(
      await screen.findByText(/3 invoice line\(s\) are categorized/i),
    ).toBeTruthy()
    const retry = await screen.findByRole('button', { name: /delete anyway/i })
    fireEvent.click(retry)

    await waitFor(() =>
      expect(onDelete).toHaveBeenLastCalledWith({ id: 'tree1', confirm: true }),
    )
  })

  it('keeps a tree that is still in use, showing the reason', async () => {
    const onDelete = vi.fn().mockRejectedValue({
      detail:
        'This tree is in use by Acme A/S. Assign those companies another tree first.',
    })
    renderPanel({ onDelete })

    fireEvent.click(
      screen.getByRole('button', { name: /actions for default spend tree/i }),
    )
    fireEvent.click(await screen.findByRole('menuitem', { name: /delete/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }))

    expect(await screen.findByText(/in use by Acme A\/S/i)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /delete anyway/i })).toBeNull()
  })

  it('cancelling deletes nothing', async () => {
    const onDelete = vi.fn()
    renderPanel({ onDelete })

    fireEvent.click(
      screen.getByRole('button', { name: /actions for default spend tree/i }),
    )
    fireEvent.click(await screen.findByRole('menuitem', { name: /delete/i }))
    fireEvent.click(await screen.findByRole('button', { name: /cancel/i }))

    expect(onDelete).not.toHaveBeenCalled()
  })

  it('offers no row actions to a read-only member', () => {
    renderPanel({ canManage: false, onDelete: vi.fn() })
    expect(screen.queryByRole('button', { name: /actions for/i })).toBeNull()
  })
})
