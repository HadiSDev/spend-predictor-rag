import * as React from 'react'
import { Check, ChevronRight, Search, X } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger, cn } from '#/components/ui'
import { childrenOf, formatPath, nodePath } from '#/lib/spend-trees'
import type { SpendCategoryRead } from '#/lib/types'

export interface TreeSelectorProps {
  nodes: Array<SpendCategoryRead>
  /** The currently chosen node, or null when nothing has been picked. */
  value: string | null
  onChange: (node: SpendCategoryRead) => void
  disabled?: boolean
  /** Shown on the trigger when nothing is chosen. */
  placeholder?: string
  /**
   * The path a previous decision recorded, when it no longer resolves to a
   * node. Rendered as the trigger's subtext so a reviewer can see what the line
   * *was* categorized as while choosing what it should be now.
   */
  previousPath?: Array<string> | null
  id?: string
}

/** How many columns to render — the depth the tree actually uses. */
function treeDepth(nodes: Array<SpendCategoryRead>): number {
  return nodes.reduce((deepest, node) => Math.max(deepest, node.depth), 1)
}

/** The chain of ancestors from the root down to `node`, inclusive. */
function ancestry(
  nodes: Array<SpendCategoryRead>,
  node: SpendCategoryRead | undefined,
): Array<string> {
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const chain: Array<string> = []
  let cursor = node
  while (cursor) {
    chain.unshift(cursor.id)
    cursor = cursor.parent_id ? byId.get(cursor.parent_id) : undefined
  }
  return chain
}

/**
 * Pick a spend category from the company's tree.
 *
 * **Columns, not an accordion.** The taxonomy is wide and shallow — hundreds of
 * nodes over three or four levels — so an indented accordion is a scroll-hunt
 * where three side-by-side columns are two clicks. Columns also make the path
 * legible while navigating: you can see where in the taxonomy you are, not just
 * what you last expanded.
 *
 * Search switches the panel to a flat list of full paths, because someone who
 * knows the leaf they want should not have to drill to it.
 *
 * Choosing a **non-leaf is allowed**: a three-level tree's level-2 node is a
 * legitimate answer, and refusing it would force a false precision the customer
 * did not ask for.
 */
export function TreeSelector({
  nodes,
  value,
  onChange,
  disabled = false,
  placeholder = 'Choose a category',
  previousPath = null,
  id,
}: TreeSelectorProps) {
  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState('')
  const [path, setPath] = React.useState<Array<string>>([])

  const selected = React.useMemo(
    () => nodes.find((node) => node.id === value),
    [nodes, value],
  )

  // Opening lands on the chosen node's own branch rather than at the roots —
  // the common case is adjusting a category, not picking one from scratch.
  React.useEffect(() => {
    if (open) {
      setQuery('')
      setPath(ancestry(nodes, selected).slice(0, -1))
    }
  }, [open, nodes, selected])

  const depth = treeDepth(nodes)
  const columns: Array<Array<SpendCategoryRead>> = []
  for (let level = 0; level < depth; level += 1) {
    const parentId = level === 0 ? null : (path[level - 1] ?? undefined)
    if (parentId === undefined) break
    const items = childrenOf(nodes, parentId)
    if (items.length === 0) break
    columns.push(items)
  }

  const matches = React.useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return []
    return nodes
      .filter((node) => formatPath(node).toLowerCase().includes(needle))
      .slice(0, 50)
  }, [nodes, query])

  function choose(node: SpendCategoryRead) {
    onChange(node)
    setOpen(false)
  }

  function openBranch(level: number, node: SpendCategoryRead) {
    // Selecting in a column both drills in and *is* a valid answer — a parent
    // node is a legitimate category. Drilling keeps the popup open; the choose
    // button in the footer commits.
    setPath([...path.slice(0, level), node.id])
  }

  const current = path.length > 0 ? nodes.find((n) => n.id === path[path.length - 1]) : undefined

  return (
    <Popover open={open} onOpenChange={disabled ? undefined : setOpen}>
      <PopoverTrigger
        id={id}
        disabled={disabled}
        className={cn(
          // Solid and bordered, not a ghost field: this is the anchor of the
          // editor and the one control a reviewer is here to use.
          'flex w-full items-center justify-between gap-3 rounded-md border border-input bg-card px-3 py-2 text-left shadow-sm outline-none transition',
          'hover:border-ring focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring',
          'disabled:cursor-not-allowed disabled:opacity-50',
        )}
      >
        <span className="min-w-0">
          {selected ? (
            <PathText path={nodePath(selected)} />
          ) : previousPath && previousPath.length > 0 ? (
            <span className="block">
              <span className="block text-sm font-medium text-foreground">{placeholder}</span>
              <span className="block truncate text-xs text-muted-foreground">
                Previously {previousPath.join(' › ')}
              </span>
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">{placeholder}</span>
          )}
        </span>
        <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </PopoverTrigger>

      <PopoverContent align="start" className="w-[min(48rem,90vw)] p-0">
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search all categories"
            aria-label="Search all categories"
            className="h-8 w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
          {query ? (
            <button
              type="button"
              onClick={() => setQuery('')}
              aria-label="Clear search"
              className="rounded p-1 text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          ) : null}
        </div>

        {query.trim() ? (
          <SearchResults matches={matches} value={value} onChoose={choose} />
        ) : (
          <div className="flex max-h-80 divide-x divide-border overflow-x-auto">
            {columns.map((items, level) => (
              <Column
                key={level}
                items={items}
                activeId={path[level] ?? null}
                selectedId={value}
                onOpen={(node) => openBranch(level, node)}
                onChoose={choose}
              />
            ))}
          </div>
        )}

        {current && !query.trim() ? (
          <div className="flex items-center justify-between gap-3 border-t border-border px-3 py-2">
            <PathText path={nodePath(current)} />
            <button
              type="button"
              onClick={() => choose(current)}
              className="shrink-0 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:opacity-90"
            >
              Use this category
            </button>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  )
}

/** The chosen path, with the leaf carrying the weight. */
function PathText({ path }: { path: Array<string> }) {
  if (path.length === 0) return null
  const leaf = path[path.length - 1]
  const ancestors = path.slice(0, -1)
  return (
    <span className="block min-w-0">
      {ancestors.length > 0 ? (
        <span className="block truncate text-xs text-muted-foreground">
          {ancestors.join(' › ')}
        </span>
      ) : null}
      <span className="block truncate text-sm font-medium text-foreground">{leaf}</span>
    </span>
  )
}

interface ColumnProps {
  items: Array<SpendCategoryRead>
  activeId: string | null
  selectedId: string | null
  onOpen: (node: SpendCategoryRead) => void
  onChoose: (node: SpendCategoryRead) => void
}

function Column({ items, activeId, selectedId, onOpen, onChoose }: ColumnProps) {
  return (
    <ul className="min-w-52 flex-1 overflow-y-auto py-1" role="group">
      {items.map((node) => {
        const active = node.id === activeId
        const chosen = node.id === selectedId
        return (
          <li key={node.id}>
            <button
              type="button"
              onClick={() => onOpen(node)}
              onDoubleClick={() => onChoose(node)}
              aria-current={active ? 'true' : undefined}
              className={cn(
                'flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm transition',
                active ? 'bg-muted font-medium text-foreground' : 'text-foreground hover:bg-muted/60',
              )}
            >
              <span className="truncate">{node.name}</span>
              <span className="flex shrink-0 items-center gap-1">
                {chosen ? <Check className="size-3.5 text-primary" aria-label="Selected" /> : null}
                <ChevronRight className="size-3.5 text-muted-foreground" aria-hidden />
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

function SearchResults({
  matches,
  value,
  onChoose,
}: {
  matches: Array<SpendCategoryRead>
  value: string | null
  onChoose: (node: SpendCategoryRead) => void
}) {
  if (matches.length === 0) {
    return (
      <p className="px-3 py-6 text-center text-sm text-muted-foreground">
        No categories match that search.
      </p>
    )
  }
  return (
    <ul className="max-h-80 overflow-y-auto py-1">
      {matches.map((node) => (
        <li key={node.id}>
          <button
            type="button"
            onClick={() => onChoose(node)}
            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left transition hover:bg-muted/60"
          >
            {/* The full path, because a leaf name alone is ambiguous across a
                taxonomy — "Software" says nothing about which branch. */}
            <PathText path={nodePath(node)} />
            {node.id === value ? (
              <Check className="size-4 shrink-0 text-primary" aria-label="Selected" />
            ) : null}
          </button>
        </li>
      ))}
    </ul>
  )
}
