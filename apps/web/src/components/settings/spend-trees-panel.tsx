import * as React from 'react'
import { Archive, Copy, FileUp, MoreHorizontal, Plus, Sparkles, Trash2 } from 'lucide-react'
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
  Dialog,
  DialogContent,
  DialogTitle,
  Field,
  FieldControl,
  FieldLabel,
  RadioGroup,
  RadioItem,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Textarea,
  cn,
} from '#/components/ui'
import type {
  SpendTreeCreate,
  SpendTreeImportError,
  SpendTreeImportResult,
  SpendTreeRead,
} from '#/lib/types'

/** How a new tree starts out. All three end in the same node rows. */
type Start = 'clone' | 'empty' | 'import'

/** Only 3 or 4: the server rejects anything else, and a free number field
 *  would invite a value that cannot be saved. */
const DEPTH_ITEMS = [
  { value: '3', label: '3 levels' },
  { value: '4', label: '4 levels' },
]

export interface SpendTreesPanelProps {
  trees: Array<SpendTreeRead>
  loading?: boolean
  error?: boolean
  canManage: boolean
  onCreate: (body: SpendTreeCreate) => Promise<SpendTreeRead>
  /** Materialize the organization's copy of the default template. */
  onUseDefault?: () => Promise<unknown>
  /** Delete a tree and its nodes. `confirm` acknowledges orphaning lines. */
  onDelete?: (args: { id: string; confirm?: boolean }) => Promise<unknown>
  /** Retire a tree without deleting it. */
  onArchive?: (id: string) => Promise<unknown>
  /** Resolves with the result, or rejects. A `409` carries `affected_lines`. */
  onImport: (args: {
    treeId: string
    content: string
    mode: 'merge' | 'replace'
    confirm: boolean
  }) => Promise<SpendTreeImportResult>
  onOpenTree: (treeId: string) => void
}

/** The per-row summary a manager chooses between trees on. */
function depthLabel(tree: SpendTreeRead): string {
  return `${tree.max_depth} levels`
}

/**
 * The organization's spend trees.
 *
 * Presentational: every query and mutation lives in the route, so this renders
 * directly in tests — the same split `AccountsPanel` uses.
 */
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
  // The template is copied into an organization on first use, and creating a
  // company is the only thing that triggers it — so an organization that
  // predates spend trees has none, and no way to ask for one without this.
  const hasDefault = trees.some((tree) => tree.source === 'default_template')

  if (error) {
    return (
      <Card className="p-8 text-center">
        <h2 className="font-display text-base font-medium">Couldn’t load the spend trees</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          The request to the web API failed. Check that it is running and reachable, then reload.
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
            The taxonomy your spend is categorized into. Each company is assigned one; several
            companies can share a tree.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Suppressed while the list is empty: the empty-state card already
              carries this call to action, and two of them read as two
              different things. */}
          {!hasDefault && onUseDefault && trees.length > 0 ? (
            <Button
              variant="outline"
              disabled={!canManage || addingDefault}
              title={canManage ? undefined : 'Requires an admin or moderator role'}
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
            title={canManage ? undefined : 'Requires an admin or moderator role'}
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
          <h3 className="font-display text-base font-medium">No spend trees yet</h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            A new company gets the built-in default tree automatically. Companies created before
            spend trees existed have none — add the default here, or build your own.
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
              onClick={() => {
                setBusy(true)
                setDeleteError(null)
                void onDelete!({ id: deleting!.id, confirm: needsConfirm })
                  .then(() => {
                    setDeleting(null)
                    setNeedsConfirm(false)
                  })
                  .catch((failure: { detail?: unknown }) => {
                    const detail = failure.detail
                    setDeleteError(
                      typeof detail === 'string'
                        ? detail
                        : (failure as unknown as Error).message,
                    )
                    // A refusal naming affected lines is retryable with a
                    // confirmation; one naming companies is not, and the
                    // button below simply fails again with the same message.
                    if (typeof detail === 'string' && detail.includes('invoice line')) {
                      setNeedsConfirm(true)
                    }
                  })
                  .finally(() => setBusy(false))
              }}
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

interface CreateTreeDialogProps {
  open: boolean
  trees: Array<SpendTreeRead>
  onOpenChange: (open: boolean) => void
  onCreate: SpendTreesPanelProps['onCreate']
  onImport: SpendTreesPanelProps['onImport']
}

/**
 * The three starting points in one dialog: clone, empty, or CSV.
 *
 * Import creates the tree first and loads into it, so a rejected file leaves
 * something to retry against rather than vanishing along with the tree.
 */
function CreateTreeDialog({
  open,
  trees,
  onOpenChange,
  onCreate,
  onImport,
}: CreateTreeDialogProps) {
  const [start, setStart] = React.useState<Start>('clone')
  const [name, setName] = React.useState('')
  const [maxDepth, setMaxDepth] = React.useState('3')
  const [sourceId, setSourceId] = React.useState<string>('')
  const [csv, setCsv] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [rowErrors, setRowErrors] = React.useState<Array<SpendTreeImportError>>([])
  const [message, setMessage] = React.useState<string | null>(null)

  const defaultTree = trees.find((t) => t.source === 'default_template')
  const treeItems = React.useMemo(
    () => trees.map((tree) => ({ value: tree.id, label: tree.name })),
    [trees],
  )

  React.useEffect(() => {
    if (open) {
      setStart(defaultTree ? 'clone' : 'empty')
      setName('')
      setMaxDepth('3')
      setSourceId(defaultTree?.id ?? trees[0]?.id ?? '')
      setCsv('')
      setRowErrors([])
      setMessage(null)
    }
  }, [open, defaultTree, trees])

  // The parsed row count, shown before applying so nobody loads a file blind.
  const csvRows = React.useMemo(
    () => csv.split('\n').filter((row) => row.trim().length > 0).length,
    [csv],
  )

  async function submit() {
    setBusy(true)
    setRowErrors([])
    setMessage(null)
    try {
      const tree = await onCreate({
        name,
        max_depth: Number(maxDepth),
        source_tree_id: start === 'clone' ? sourceId : null,
      })
      if (start === 'import') {
        await onImport({ treeId: tree.id, content: csv, mode: 'merge', confirm: false })
      }
      onOpenChange(false)
    } catch (failure) {
      const detail = (failure as { detail?: unknown }).detail
      if (detail && typeof detail === 'object' && 'errors' in detail) {
        setRowErrors((detail as { errors: Array<SpendTreeImportError> }).errors)
        setMessage((detail as { message?: string }).message ?? 'The file could not be imported.')
      } else {
        setMessage(
          typeof detail === 'string' ? detail : (failure as Error).message || 'Something failed.',
        )
      }
    } finally {
      setBusy(false)
    }
  }

  const canSubmit =
    name.trim().length > 0 &&
    (start !== 'clone' || sourceId !== '') &&
    (start !== 'import' || csv.trim().length > 0)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(40rem,92vw)]">
        <DialogTitle>New spend tree</DialogTitle>

        <div className="mt-4 flex flex-col gap-4">
          <Field>
            <FieldLabel>Name</FieldLabel>
            <FieldControl value={name} onChange={(e) => setName(e.target.value)} />
          </Field>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium">Start from</legend>
            <RadioGroup value={start} onValueChange={(value) => setStart(value as Start)}>
              <label className="flex items-start gap-3 rounded-md border border-border p-3">
                <RadioItem
                  value="clone"
                  aria-label="Copy an existing tree"
                  disabled={trees.length === 0}
                />
                <span>
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <Copy className="size-4" aria-hidden /> Copy an existing tree
                  </span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    Starts as a full copy. Editing it never changes the tree you copied.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-3 rounded-md border border-border p-3">
                <RadioItem value="empty" aria-label="Start empty" />
                <span>
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <Plus className="size-4" aria-hidden /> Start empty
                  </span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    Add categories one at a time.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-3 rounded-md border border-border p-3">
                <RadioItem value="import" aria-label="Import a CSV" />
                <span>
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <FileUp className="size-4" aria-hidden /> Import a CSV
                  </span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    Columns: level_1, level_2, level_3, level_4, description, code.
                  </span>
                </span>
              </label>
            </RadioGroup>
          </fieldset>

          {start === 'clone' && trees.length > 0 ? (
            <Field>
              <FieldLabel>Copy from</FieldLabel>
              <Select
                items={treeItems}
                value={sourceId}
                onValueChange={(v) => setSourceId(String(v))}
              >
                <SelectTrigger aria-label="Copy from">
                  <SelectValue items={treeItems} />
                </SelectTrigger>
                <SelectContent>
                  {trees.map((tree) => (
                    <SelectItem key={tree.id} value={tree.id}>
                      {tree.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          ) : null}

          <Field>
            <FieldLabel>Levels</FieldLabel>
            <Select
              items={DEPTH_ITEMS}
              value={maxDepth}
              onValueChange={(v) => setMaxDepth(String(v))}
            >
              <SelectTrigger aria-label="Levels">
                <SelectValue items={DEPTH_ITEMS} />
              </SelectTrigger>
              <SelectContent>
                {DEPTH_ITEMS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          {start === 'import' ? (
            <Field>
              <FieldLabel>CSV</FieldLabel>
              <Textarea
                // A plain Textarea is not a Field.Control, so Base UI does not
                // wire the label to it — name it explicitly.
                aria-label="CSV"
                rows={8}
                value={csv}
                onChange={(e) => setCsv(e.target.value)}
                placeholder={'level_1,level_2,level_3,description,code\nIndirect,Technology,Cloud,Hosting,6010'}
              />
              {csv.trim() ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {csvRows} line{csvRows === 1 ? '' : 's'} to import, including the header.
                </p>
              ) : null}
            </Field>
          ) : null}

          {message ? <p className="text-sm text-destructive">{message}</p> : null}
          {rowErrors.length > 0 ? (
            // Per row with its file line number: a user fixes a spreadsheet by
            // going to a line, and "the import failed" sends them nowhere.
            <ul className="flex flex-col gap-1 rounded-md bg-destructive/10 p-3 text-sm">
              {rowErrors.map((row) => (
                <li key={`${row.line}-${row.message}`} className="text-destructive">
                  <span className="font-medium">Line {row.line}:</span> {row.message}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="mt-5 flex items-center justify-end gap-2">
          <Button variant="ghost" disabled={busy} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={busy || !canSubmit} onClick={() => void submit()}>
            {busy ? 'Creating…' : 'Create tree'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
