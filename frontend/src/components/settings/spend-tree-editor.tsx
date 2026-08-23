import * as React from 'react'
import { ArrowLeft, ChevronDown, ChevronRight, Pencil, Plus, Trash2 } from 'lucide-react'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Button,
  Card,
  Dialog,
  DialogContent,
  DialogTitle,
  Field,
  FieldControl,
  FieldLabel,
  IconButton,
  Skeleton,
} from '#/components/ui'
import { buildTree } from '#/lib/spend-trees'
import { TreeSuggestions } from './tree-suggestions'
import type { TreeNode } from '#/lib/spend-trees'
import type {
  SpendCategoryCreate,
  SpendCategoryUpdate,
  SpendCategorySuggestionRead,
  SpendTreeDetailRead,
} from '#/lib/types'

export interface SpendTreeEditorProps {
  tree: SpendTreeDetailRead | undefined
  loading?: boolean
  canManage: boolean
  onBack: () => void
  onAddNode: (body: SpendCategoryCreate) => Promise<unknown>
  onUpdateNode: (id: string, body: SpendCategoryUpdate) => Promise<unknown>
  /** Resolves with how many invoice lines lost their category pointer. */
  onDeleteNode: (id: string) => Promise<{ stale_lines: number }>
  /**
   * Categories this tree may be missing, proposed from the company's own spend.
   *
   * Rendered here rather than in a notifications area because accepting one *is*
   * a tree edit: the reviewer needs the tree in front of them to judge whether a
   * proposal duplicates something they already have under another name, and to
   * see where it would land.
   */
  suggestions?: Array<SpendCategorySuggestionRead>
  onAcceptSuggestion?: (id: string) => Promise<unknown>
  onDismissSuggestion?: (id: string) => Promise<unknown>
  onReopenSuggestion?: (id: string) => Promise<unknown>
}

/**
 * A tree's nodes, edited as a tree.
 *
 * The depth limit is enforced *visibly*: add-child is unavailable at the tree's
 * maximum with the reason stated, rather than offered and then rejected by the
 * server. An affordance that claims a permission it will never grant is worse
 * than no affordance — the same rule the voucher panel applies to ERP-posted
 * values.
 */
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
  const [adding, setAdding] = React.useState<{ parentId: string | null; depth: number } | null>(
    null,
  )
  const [editing, setEditing] = React.useState<TreeNode | null>(null)
  const [deleting, setDeleting] = React.useState<TreeNode | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const roots = React.useMemo(() => buildTree(tree?.nodes ?? []), [tree])

  // A newly loaded tree opens down to level 2: the roots alone are two rows and
  // say nothing, while everything expanded is a wall.
  React.useEffect(() => {
    if (tree) {
      setExpanded(new Set(tree.nodes.filter((n) => n.depth === 1).map((n) => n.id)))
    }
  }, [tree])

  function toggle(id: string) {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
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

      {suggestions && onAcceptSuggestion && onDismissSuggestion && onReopenSuggestion ? (
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
                onAdd={(parent) => setAdding({ parentId: parent.id, depth: parent.depth + 1 })}
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
            setError(typeof detail === 'string' ? detail : (failure as Error).message)
            setDeleting(null)
          }
        }}
      />
    </div>
  )
}

interface NodeRowProps {
  node: TreeNode
  maxDepth: number
  canManage: boolean
  expanded: Set<string>
  onToggle: (id: string) => void
  onAdd: (node: TreeNode) => void
  onEdit: (node: TreeNode) => void
  onDelete: (node: TreeNode) => void
}

function NodeRow({
  node,
  maxDepth,
  canManage,
  expanded,
  onToggle,
  onAdd,
  onEdit,
  onDelete,
}: NodeRowProps) {
  const open = expanded.has(node.id)
  const hasChildren = node.children.length > 0
  const atMaxDepth = node.depth >= maxDepth

  return (
    <li>
      <div
        className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50"
        style={{ paddingLeft: `${0.5 + (node.depth - 1) * 1.25}rem` }}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={() => onToggle(node.id)}
            aria-label={open ? `Collapse ${node.name}` : `Expand ${node.name}`}
            aria-expanded={open}
            className="rounded p-0.5 text-muted-foreground hover:text-foreground"
          >
            {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          </button>
        ) : (
          <span className="size-5" aria-hidden />
        )}

        <span className="min-w-0 flex-1">
          <span className="text-sm text-foreground">{node.name}</span>
          {node.code ? (
            <Badge variant="outline" className="ml-2">
              {node.code}
            </Badge>
          ) : null}
          {node.description ? (
            <span className="ml-2 truncate text-xs text-muted-foreground">{node.description}</span>
          ) : null}
        </span>

        <span className="flex shrink-0 items-center gap-1">
          <IconButton
            aria-label={`Add a category under ${node.name}`}
            disabled={!canManage || atMaxDepth}
            title={
              atMaxDepth
                ? `This tree is ${maxDepth} levels deep — its deepest categories cannot have children.`
                : canManage
                  ? undefined
                  : 'Requires an admin or moderator role'
            }
            onClick={() => onAdd(node)}
          >
            <Plus className="size-4" />
          </IconButton>
          <IconButton
            aria-label={`Edit ${node.name}`}
            disabled={!canManage}
            onClick={() => onEdit(node)}
          >
            <Pencil className="size-4" />
          </IconButton>
          <IconButton
            aria-label={`Delete ${node.name}`}
            disabled={!canManage}
            onClick={() => onDelete(node)}
          >
            <Trash2 className="size-4" />
          </IconButton>
        </span>
      </div>

      {open && hasChildren ? (
        <ul>
          {node.children.map((child) => (
            <NodeRow
              key={child.id}
              node={child}
              maxDepth={maxDepth}
              canManage={canManage}
              expanded={expanded}
              onToggle={onToggle}
              onAdd={onAdd}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

interface NodeValues {
  name: string
  code?: string | null
  description?: string | null
}

function NodeDialog({
  open,
  title,
  initial,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  title: string
  initial?: NodeValues
  onOpenChange: (open: boolean) => void
  onSubmit: (values: NodeValues) => Promise<void>
}) {
  const [name, setName] = React.useState('')
  const [code, setCode] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (open) {
      setName(initial?.name ?? '')
      setCode(initial?.code ?? '')
      setDescription(initial?.description ?? '')
      setError(null)
    }
  }, [open, initial])

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await onSubmit({ name, code: code || null, description: description || null })
    } catch (failure) {
      const detail = (failure as { detail?: unknown }).detail
      setError(typeof detail === 'string' ? detail : (failure as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(32rem,92vw)]">
        <DialogTitle>{title}</DialogTitle>
        <div className="mt-4 flex flex-col gap-3">
          <Field>
            <FieldLabel>Name</FieldLabel>
            <FieldControl value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field>
            <FieldLabel>Code (optional)</FieldLabel>
            <FieldControl value={code} onChange={(e) => setCode(e.target.value)} />
          </Field>
          <Field>
            <FieldLabel>Description (optional)</FieldLabel>
            <FieldControl
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        <div className="mt-5 flex items-center justify-end gap-2">
          <Button variant="ghost" disabled={busy} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={busy || name.trim().length === 0} onClick={() => void submit()}>
            {busy ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Deleting states its cost before it happens.
 *
 * A node with children is refused by the server, so the dialog says so rather
 * than letting a manager discover it as an error — deleting a subtree by
 * deleting its root is easy to do by accident and impossible to undo.
 */
function DeleteNodeDialog({
  node,
  onOpenChange,
  onConfirm,
}: {
  node: TreeNode | null
  onOpenChange: (open: boolean) => void
  onConfirm: () => Promise<void>
}) {
  const childCount = node?.children.length ?? 0
  return (
    <AlertDialog open={node !== null} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete “{node?.name}”?</AlertDialogTitle>
          <AlertDialogDescription>
          {childCount > 0 ? (
            <>
              This category has {childCount} sub-categor{childCount === 1 ? 'y' : 'ies'}. Delete or
              move {childCount === 1 ? 'it' : 'them'} first.
            </>
          ) : (
            <>
              Invoice lines assigned to this category keep the category on record but will need
              reviewing.
            </>
          )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={childCount > 0}
            onClick={() => void onConfirm()}
          >
            Delete
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
