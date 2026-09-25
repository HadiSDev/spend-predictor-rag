import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { TreeSelector } from './tree-selector'
import type { SpendCategoryRead } from '#/lib/api/types'

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

/** A four-level tree: Indirect > Technology > Cloud > {Compute, Storage}. */
const DEEP: Array<SpendCategoryRead> = [
  node('n1', 1, 'Indirect', null, ['Indirect']),
  node('n2', 1, 'Direct', null, ['Direct']),
  node('n3', 2, 'Technology', 'n1', ['Indirect', 'Technology']),
  node('n4', 3, 'Cloud', 'n3', ['Indirect', 'Technology', 'Cloud']),
  node('n5', 4, 'Compute', 'n4', [
    'Indirect',
    'Technology',
    'Cloud',
    'Compute',
  ]),
  node('n6', 4, 'Storage', 'n4', [
    'Indirect',
    'Technology',
    'Cloud',
    'Storage',
  ]),
]

/** The popup portals to the end of the body, so the last match is inside it. */
function inPopup(matches: Array<HTMLElement>): HTMLElement {
  return matches[matches.length - 1]
}

describe('TreeSelector', () => {
  it('shows the chosen node as its full path, with the leaf carrying the weight', () => {
    render(<TreeSelector nodes={DEEP} value="n5" onChange={vi.fn()} />)
    const trigger = screen.getByRole('button')
    expect(
      within(trigger).getByText('Indirect › Technology › Cloud'),
    ).toBeTruthy()
    expect(within(trigger).getByText('Compute')).toBeTruthy()
  })

  it('drills level by level and sends the whole node on choose', async () => {
    const onChange = vi.fn()
    render(<TreeSelector nodes={DEEP} value={null} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /choose a category/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^Indirect$/ }))
    fireEvent.click(await screen.findByRole('button', { name: /^Technology$/ }))
    fireEvent.click(await screen.findByRole('button', { name: /^Cloud$/ }))
    fireEvent.click(await screen.findByRole('button', { name: /^Compute$/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /use this category/i }),
    )

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ id: 'n5' }))
  })

  it('presents a fourth level in the same control, with no extra input', async () => {
    render(<TreeSelector nodes={DEEP} value={null} onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /choose a category/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^Indirect$/ }))
    fireEvent.click(await screen.findByRole('button', { name: /^Technology$/ }))
    fireEvent.click(await screen.findByRole('button', { name: /^Cloud$/ }))

    expect(
      await screen.findByRole('button', { name: /^Compute$/ }),
    ).toBeTruthy()
    expect(
      await screen.findByRole('button', { name: /^Storage$/ }),
    ).toBeTruthy()
    expect(screen.queryByLabelText(/level 4/i)).toBeNull()
  })

  it('reaches a deep leaf by search, listing full paths', async () => {
    const onChange = vi.fn()
    render(<TreeSelector nodes={DEEP} value={null} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /choose a category/i }))
    fireEvent.change(await screen.findByLabelText(/search all categories/i), {
      target: { value: 'storage' },
    })

    const match = inPopup(
      await screen.findAllByRole('button', { name: /Cloud.*Storage/ }),
    )
    fireEvent.click(match)
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ id: 'n6' }))
  })

  it('says so when a search matches nothing', async () => {
    render(<TreeSelector nodes={DEEP} value={null} onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /choose a category/i }))
    fireEvent.change(await screen.findByLabelText(/search all categories/i), {
      target: { value: 'zzzz' },
    })
    expect(await screen.findByText(/no categories match/i)).toBeTruthy()
  })

  it('allows choosing a non-leaf node', async () => {
    const onChange = vi.fn()
    render(<TreeSelector nodes={DEEP} value={null} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /choose a category/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^Indirect$/ }))
    fireEvent.click(
      await screen.findByRole('button', { name: /use this category/i }),
    )

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ id: 'n1' }))
  })

  it('opens on the chosen node’s own branch', async () => {
    render(<TreeSelector nodes={DEEP} value="n5" onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button'))

    expect(await screen.findByRole('button', { name: /^Compute/ })).toBeTruthy()
  })

  it('shows a previous path when the stored category no longer resolves', () => {
    render(
      <TreeSelector
        nodes={DEEP}
        value={null}
        onChange={vi.fn()}
        previousPath={['Indirect', 'Machinery']}
      />,
    )
    expect(screen.getByText(/Previously Indirect › Machinery/)).toBeTruthy()
  })

  it('does not open when disabled', () => {
    render(
      <TreeSelector nodes={DEEP} value={null} onChange={vi.fn()} disabled />,
    )
    const trigger = screen.getByRole('button')
    fireEvent.click(trigger)
    expect(screen.queryByLabelText(/search all categories/i)).toBeNull()
  })

  it('marks the chosen node in its column', async () => {
    render(<TreeSelector nodes={DEEP} value="n5" onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button'))
    const chosen = await screen.findByRole('button', { name: /^Compute/ })
    expect(within(chosen).getByLabelText(/selected/i)).toBeTruthy()
  })
})
