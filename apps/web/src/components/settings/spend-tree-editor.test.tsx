import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { SpendTreeEditor } from './spend-tree-editor'
import type { SpendCategoryRead, SpendTreeDetailRead } from '#/lib/types'

function node(
  id: string,
  depth: number,
  name: string,
  parent_id: string | null,
  levels: Array<string | null>,
): SpendCategoryRead {
  return {
    id,
    spend_tree_id: 'tree1',
    parent_id,
    depth,
    name,
    code: null,
    sort_order: 0,
    description: null,
    level_1: levels[0] ?? null,
    level_2: levels[1] ?? null,
    level_3: levels[2] ?? null,
    level_4: levels[3] ?? null,
  }
}

function tree(maxDepth = 3): SpendTreeDetailRead {
  const nodes = [
    node('n1', 1, 'Indirect', null, ['Indirect']),
    node('n2', 2, 'Technology', 'n1', ['Indirect', 'Technology']),
    node('n3', 3, 'Cloud', 'n2', ['Indirect', 'Technology', 'Cloud']),
  ]
  return {
    id: 'tree1',
    name: 'Our tree',
    max_depth: maxDepth,
    source: 'custom',
    template_version: null,
    archived_at: null,
    created_at: '2026-07-01T00:00:00Z',
    node_count: nodes.length,
    company_ids: [],
    company_names: [],
    nodes,
  }
}

function renderEditor(overrides: Partial<React.ComponentProps<typeof SpendTreeEditor>> = {}) {
  const props = {
    tree: tree(),
    canManage: true,
    onBack: vi.fn(),
    onAddNode: vi.fn().mockResolvedValue(undefined),
    onUpdateNode: vi.fn().mockResolvedValue(undefined),
    onDeleteNode: vi.fn().mockResolvedValue({ stale_lines: 0 }),
    ...overrides,
  }
  render(<SpendTreeEditor {...props} />)
  return props
}

describe('SpendTreeEditor', () => {
  it('renders the hierarchy, not a flat list of level columns', () => {
    renderEditor()
    expect(screen.getByText('Indirect')).toBeTruthy()
    // Level 1 is expanded by default; deeper levels are reachable, not dumped.
    expect(screen.getByText('Technology')).toBeTruthy()
    expect(screen.getByRole('button', { name: /expand technology/i })).toBeTruthy()
  })

  it('expands and collapses a branch', () => {
    renderEditor()
    fireEvent.click(screen.getByRole('button', { name: /expand technology/i }))
    expect(screen.getByText('Cloud')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /collapse technology/i }))
    expect(screen.queryByText('Cloud')).toBeNull()
  })

  it('adds a child under a node', async () => {
    const props = renderEditor()
    fireEvent.click(screen.getByRole('button', { name: /add a category under technology/i }))

    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Telecom' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(props.onAddNode).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Telecom', parent_id: 'n2' }),
      ),
    )
  })

  it('makes the depth limit visible before it bites', () => {
    // An affordance that claims a permission it will never grant is worse than
    // no affordance.
    renderEditor()
    fireEvent.click(screen.getByRole('button', { name: /expand technology/i }))

    const add = screen.getByRole('button', { name: /add a category under cloud/i })
    expect(add).toHaveProperty('disabled', true)
    expect(add.getAttribute('title')).toMatch(/3 levels deep/i)
  })

  it('allows a fourth level on a four-level tree', () => {
    renderEditor({ tree: tree(4) })
    fireEvent.click(screen.getByRole('button', { name: /expand technology/i }))
    expect(
      screen.getByRole('button', { name: /add a category under cloud/i }),
    ).toHaveProperty('disabled', false)
  })

  it('refuses to delete a node with children, and says why', async () => {
    const props = renderEditor()
    fireEvent.click(screen.getByRole('button', { name: /delete technology/i }))

    expect(await screen.findByText(/1 sub-category/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /^delete$/i })).toHaveProperty('disabled', true)
    expect(props.onDeleteNode).not.toHaveBeenCalled()
  })

  it('warns that assigned lines will need reviewing before deleting a leaf', async () => {
    const props = renderEditor()
    fireEvent.click(screen.getByRole('button', { name: /expand technology/i }))
    fireEvent.click(screen.getByRole('button', { name: /delete cloud/i }))

    expect(await screen.findByText(/keep the category on record but will need reviewing/i))
      .toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(props.onDeleteNode).toHaveBeenCalledWith('n3'))
  })

  it('cancelling a delete changes nothing', async () => {
    const props = renderEditor()
    fireEvent.click(screen.getByRole('button', { name: /expand technology/i }))
    fireEvent.click(screen.getByRole('button', { name: /delete cloud/i }))
    fireEvent.click(await screen.findByRole('button', { name: /cancel/i }))
    expect(props.onDeleteNode).not.toHaveBeenCalled()
  })

  it('withholds every mutating control from a read-only member', () => {
    renderEditor({ canManage: false })
    expect(screen.getByRole('button', { name: /top-level category/i })).toHaveProperty(
      'disabled',
      true,
    )
    expect(screen.getByRole('button', { name: /edit technology/i })).toHaveProperty(
      'disabled',
      true,
    )
    expect(screen.getByRole('button', { name: /delete technology/i })).toHaveProperty(
      'disabled',
      true,
    )
  })

  it('renames a node', async () => {
    const props = renderEditor()
    fireEvent.click(screen.getByRole('button', { name: /edit technology/i }))

    const name = await screen.findByLabelText('Name')
    expect((name as HTMLInputElement).value).toBe('Technology')
    fireEvent.change(name, { target: { value: 'IT' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(props.onUpdateNode).toHaveBeenCalledWith('n2', expect.objectContaining({ name: 'IT' })),
    )
  })
})
