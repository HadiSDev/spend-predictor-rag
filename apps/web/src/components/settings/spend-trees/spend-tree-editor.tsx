import * as React from 'react'
import { ArrowLeft, Plus } from 'lucide-react'
import { Button, Card, IconButton, Skeleton } from '#/components/ui'
import { buildTree } from '#/lib/api/spend-trees'
import { TreeSuggestions } from './tree-suggestions'
import type { TreeNode } from '#/lib/api/spend-trees'
import type {
  SpendCategoryCreate,
  SpendCategoryUpdate,
  SpendCategorySuggestionRead,
  SpendTreeDetailRead,
} from '#/lib/api/types'
import { DeleteNodeDialog } from './delete-node-dialog'
import { NodeDialog } from './node-dialog'
import { NodeRow } from './node-row'

export interface SpendTreeEditorProps {
  tree: SpendTreeDetailRead | undefined
  loading?: boolean
  canManage: boolean
  onBack: () => void
  onAddNode: (body: SpendCategoryCreate) => Promise<unknown>
  onUpdateNode: (id: string, body: SpendCategoryUpdate) => Promise<unknown>
  /** Resolves with how many invoice lines lost their category pointer. */
  onDeleteNode: (id: string) => Promise<{ stale_lines: number }>
  /** Categories this tree may be missing, proposed from the company's own spend. */
  suggestions?: Array<SpendCategorySuggestionRead>
  onAcceptSuggestion?: (id: string) => Promise<unknown>
  onDismissSuggestion?: (id: string) => Promise<unknown>
  onReopenSuggestion?: (id: string) => Promise<unknown>
}

/** A tree's nodes, edited as a tree. */
export function SpendTreeEditor({
  tree,
  loading,
  canManage,
  onBack,
  onAddNode,
  onUpdateNode,
  onDeleteNode,
  suggestions,
  onAcceptSuggestion,
  onDismissSuggestion,
  onReopenSuggestion,
}: SpendTreeEditorProps) {
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set())
  const [adding, setAdding] = React.useState<{
    parentId: string | null
    depth: number
  } | null>(null)
  const [editing, setEditing] = React.useState<TreeNode | null>(null)
  const [deleting, setDeleting] = React.useState<TreeNode | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const roots = React.useMemo(() => buildTree(tree?.nodes ?? []), [tree])

  React.useEffect(() => {
    if (tree) {
      setExpanded(
        new Set(tree.nodes.filter((n) => n.depth === 1).map((n) => n.id)),
      )
    }
  }, [tree])

  function toggle(id: string) {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  if (loading || !tree) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <IconButton aria-label="Back to spend trees" onClick={onBack}>
            <ArrowLeft className="size-4" />
          </IconButton>
          <div>
            <h2 className="font-display text-lg font-medium">{tree.name}</h2>
            <p className="text-xs text-muted-foreground">
              {tree.max_depth} levels · {tree.node_count} categories
              {tree.source === 'default_template' ? ' · the default tree' : ''}
            </p>
          </div>
        </div>
        <Button
          disabled={!canManage}
          title={canManage ? undefined : 'Requires an admin or moderator role'}
          onClick={() => setAdding({ parentId: null, depth: 1 })}
        >
          <Plus className="size-4" /> Top-level category
        </Button>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {suggestions &&
      onAcceptSuggestion &&
      onDismissSuggestion &&
      onReopenSuggestion ? (
        <TreeSuggestions
          suggestions={suggestions}
          canManage={canManage}
          onAccept={onAcceptSuggestion}
          onDismiss={onDismissSuggestion}
          onReopen={onReopenSuggestion}
        />
      ) : null}

      <Card className="p-2">
        {roots.length === 0 ? (
          <p className="px-3 py-8 text-center text-sm text-muted-foreground">
            This tree has no categories yet.
          </p>
        ) : (
          <ul>
            {roots.map((node) => (
              <NodeRow
                key={node.id}
                node={node}
                maxDepth={tree.max_depth}
                canManage={canManage}
                expanded={expanded}
                onToggle={toggle}
                onAdd={(parent) =>
                  setAdding({ parentId: parent.id, depth: parent.depth + 1 })
                }
                onEdit={setEditing}
                onDelete={setDeleting}
              />
            ))}
          </ul>
        )}
      </Card>

      <NodeDialog
        open={adding !== null}
        title="New category"
        onOpenChange={(open) => !open && setAdding(null)}
        onSubmit={async (values) => {
          await onAddNode({ ...values, parent_id: adding?.parentId ?? null })
          setAdding(null)
        }}
      />

      <NodeDialog
        open={editing !== null}
        title="Edit category"
        initial={editing ?? undefined}
        onOpenChange={(open) => !open && setEditing(null)}
        onSubmit={async (values) => {
          await onUpdateNode(editing!.id, values)
          setEditing(null)
        }}
      />

      <DeleteNodeDialog
        node={deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        onConfirm={async () => {
          setError(null)
          try {
            await onDeleteNode(deleting!.id)
            setDeleting(null)
          } catch (failure) {
            const detail = (failure as { detail?: unknown }).detail
            setError(
              typeof detail === 'string' ? detail : (failure as Error).message,
            )
            setDeleting(null)
          }
        }}
      />
    </div>
  )
}
