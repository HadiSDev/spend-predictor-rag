import * as React from 'react'
import { Archive, MoreHorizontal, Plus, Sparkles, Trash2 } from 'lucide-react'
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  IconButton,
  Skeleton,
  cn,
} from '#/components/ui'
import type {
  SpendTreeCreate,
  SpendTreeImportResult,
  SpendTreeRead,
} from '#/lib/api/types'
import { CreateTreeDialog } from './create-tree-dialog'

export interface SpendTreesPanelProps {
  trees: Array<SpendTreeRead>
  loading?: boolean
  error?: boolean
  canManage: boolean
  onCreate: (body: SpendTreeCreate) => Promise<SpendTreeRead>
  /** Materialize the organization's copy of the default template. */
  onUseDefault?: () => Promise<unknown>
  /** Delete a tree and its nodes; `confirm` acknowledges orphaning lines. */
  onDelete?: (args: { id: string; confirm?: boolean }) => Promise<unknown>
  /** Retire a tree without deleting it. */
  onArchive?: (id: string) => Promise<unknown>
  onImport: (args: {
    treeId: string
    content: string
    mode: 'merge' | 'replace'
    confirm: boolean
  }) => Promise<SpendTreeImportResult>
  onOpenTree: (treeId: string) => void
}

function failureDetail(failure: unknown): string | undefined {
  if (
    typeof failure !== 'object' ||
    failure === null ||
    !('detail' in failure)
  ) {
    return undefined
  }
  return typeof failure.detail === 'string' ? failure.detail : undefined
}

function describeFailure(failure: unknown): string {
  return failure instanceof Error
    ? failure.message
    : 'The tree could not be deleted.'
}

function isOrphaningLinesRefusal(detail: string): boolean {
  return detail.includes('invoice line')
}

function depthLabel(tree: SpendTreeRead): string {
  return `${tree.max_depth} levels`
}

/** The organization's spend trees. */
export function SpendTreesPanel({
  trees,
  loading,
  error,
  canManage,
  onCreate,
  onUseDefault,
  onDelete,
  onArchive,
  onImport,
  onOpenTree,
}: SpendTreesPanelProps) {
  const [creating, setCreating] = React.useState(false)
  const [addingDefault, setAddingDefault] = React.useState(false)
  const [deleting, setDeleting] = React.useState<SpendTreeRead | null>(null)
  const [deleteError, setDeleteError] = React.useState<string | null>(null)
  const [needsConfirm, setNeedsConfirm] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const hasDefault = trees.some((tree) => tree.source === 'default_template')

  async function deleteTree() {
    if (!onDelete || !deleting) {
      return
    }
    setBusy(true)
    setDeleteError(null)
    try {
      await onDelete({ id: deleting.id, confirm: needsConfirm })
      setDeleting(null)
      setNeedsConfirm(false)
    } catch (failure) {
      const detail = failureDetail(failure)
      setDeleteError(detail ?? describeFailure(failure))
      if (detail !== undefined && isOrphaningLinesRefusal(detail)) {
        setNeedsConfirm(true)
      }
    } finally {
      setBusy(false)
    }
  }

  if (error) {
    return (
      <Card className="p-8 text-center">
        <h2 className="font-display text-base font-medium">
          Couldn’t load the spend trees
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          The request to the web API failed. Check that it is running and
          reachable, then reload.
        </p>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-medium">Spend trees</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            The taxonomy your spend is categorized into. Each company is
            assigned one; several companies can share a tree.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!hasDefault && onUseDefault && trees.length > 0 ? (
            <Button
              variant="outline"
              disabled={!canManage || addingDefault}
              title={
                canManage ? undefined : 'Requires an admin or moderator role'
              }
              onClick={() => {
                setAddingDefault(true)
                void onUseDefault().finally(() => setAddingDefault(false))
              }}
            >
              <Sparkles className="size-4" />
              {addingDefault ? 'Adding…' : 'Add the default tree'}
            </Button>
          ) : null}
          <Button
            disabled={!canManage}
            title={
              canManage ? undefined : 'Requires an admin or moderator role'
            }
            onClick={() => setCreating(true)}
          >
            <Plus className="size-4" /> New tree
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : trees.length === 0 ? (
        <Card className="p-8 text-center">
          <h3 className="font-display text-base font-medium">
            No spend trees yet
          </h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            A new company gets the built-in default tree automatically.
            Companies created before spend trees existed have none — add the
            default here, or build your own.
          </p>
          {onUseDefault ? (
            <Button
              className="mt-4"
              disabled={!canManage || addingDefault}
              onClick={() => {
                setAddingDefault(true)
                void onUseDefault().finally(() => setAddingDefault(false))
              }}
            >
              <Sparkles className="size-4" />
              {addingDefault ? 'Adding…' : 'Add the default tree'}
            </Button>
          ) : null}
        </Card>
      ) : (
        <ul className="flex flex-col gap-2">
          {trees.map((tree) => (
            <li
              key={tree.id}
              className={cn(
                'flex items-center gap-2 rounded-lg border border-border bg-card pr-2 shadow-sm transition',
                'focus-within:border-ring hover:border-ring',
              )}
            >
              <button
                type="button"
                onClick={() => onOpenTree(tree.id)}
                className="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-3 rounded-lg px-4 py-3 text-left outline-none"
              >
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                    {tree.name}
                    {tree.source === 'default_template' ? (
                      <Badge variant="outline">
                        <Sparkles className="size-3" aria-hidden /> Default
                      </Badge>
                    ) : null}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    {depthLabel(tree)} · {tree.node_count} categories ·{' '}
                    {tree.company_names.length > 0
                      ? `Used by ${tree.company_names.join(', ')}`
                      : 'Not assigned to a company'}
                  </p>
                </div>
              </button>
              {canManage && (onDelete || onArchive) ? (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <IconButton aria-label={`Actions for ${tree.name}`}>
                        <MoreHorizontal className="size-4" />
                      </IconButton>
                    }
                  />
                  <DropdownMenuContent>
                    {onArchive ? (
                      <DropdownMenuItem onClick={() => void onArchive(tree.id)}>
                        <Archive className="size-4" /> Archive
                      </DropdownMenuItem>
                    ) : null}
                    {onDelete ? (
                      <DropdownMenuItem
                        onClick={() => {
                          setDeleting(tree)
                          setDeleteError(null)
                          setNeedsConfirm(false)
                        }}
                      >
                        <Trash2 className="size-4" /> Delete
                      </DropdownMenuItem>
                    ) : null}
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <AlertDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null)
            setDeleteError(null)
            setNeedsConfirm(false)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{deleting?.name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteError ??
                'The tree and its categories are removed. Companies assigned to it must be ' +
                  'moved to another tree first.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => {
                setDeleting(null)
                setDeleteError(null)
                setNeedsConfirm(false)
              }}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={busy || !onDelete}
              onClick={() => void deleteTree()}
            >
              {busy ? 'Deleting…' : needsConfirm ? 'Delete anyway' : 'Delete'}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <CreateTreeDialog
        open={creating}
        trees={trees}
        onOpenChange={setCreating}
        onCreate={onCreate}
        onImport={onImport}
      />
    </div>
  )
}
