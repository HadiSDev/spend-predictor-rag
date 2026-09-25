import * as React from 'react'
import { Copy, FileUp, Plus } from 'lucide-react'
import {
  Button,
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
  Textarea,
} from '#/components/ui'
import type { SpendTreeImportError, SpendTreeRead } from '#/lib/api/types'
import type { SpendTreesPanelProps } from './spend-trees-panel'

/** How a new tree starts out. */
type Start = 'clone' | 'empty' | 'import'

/** The tree depths the server accepts. */
const DEPTH_ITEMS = [
  { value: '3', label: '3 levels' },
  { value: '4', label: '4 levels' },
]

export interface CreateTreeDialogProps {
  open: boolean
  trees: Array<SpendTreeRead>
  onOpenChange: (open: boolean) => void
  onCreate: SpendTreesPanelProps['onCreate']
  onImport: SpendTreesPanelProps['onImport']
}

/** The three starting points in one dialog: clone, empty, or CSV. */
export function CreateTreeDialog({
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
  const [rowErrors, setRowErrors] = React.useState<Array<SpendTreeImportError>>(
    [],
  )
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
        await onImport({
          treeId: tree.id,
          content: csv,
          mode: 'merge',
          confirm: false,
        })
      }
      onOpenChange(false)
    } catch (failure) {
      const detail = (failure as { detail?: unknown }).detail
      if (detail && typeof detail === 'object' && 'errors' in detail) {
        setRowErrors((detail as { errors: Array<SpendTreeImportError> }).errors)
        setMessage(
          (detail as { message?: string }).message ??
            'The file could not be imported.',
        )
      } else {
        setMessage(
          typeof detail === 'string'
            ? detail
            : (failure as Error).message || 'Something failed.',
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
            <FieldControl
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium">Start from</legend>
            <RadioGroup
              value={start}
              onValueChange={(value) => setStart(value as Start)}
            >
              <label className="flex items-start gap-3 rounded-md border border-border p-3">
                <RadioItem
                  value="clone"
                  aria-label="Copy an existing tree"
                  disabled={trees.length === 0}
                />
                <span>
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <Copy className="size-4" aria-hidden /> Copy an existing
                    tree
                  </span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    Starts as a full copy. Editing it never changes the tree you
                    copied.
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
                    Columns: level_1, level_2, level_3, level_4, description,
                    code.
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
                aria-label="CSV"
                rows={8}
                value={csv}
                onChange={(e) => setCsv(e.target.value)}
                placeholder={
                  'level_1,level_2,level_3,description,code\nIndirect,Technology,Cloud,Hosting,6010'
                }
              />
              {csv.trim() ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {csvRows} line{csvRows === 1 ? '' : 's'} to import, including
                  the header.
                </p>
              ) : null}
            </Field>
          ) : null}

          {message ? (
            <p className="text-sm text-destructive">{message}</p>
          ) : null}
          {rowErrors.length > 0 ? (
            <ul className="flex flex-col gap-1 rounded-md bg-destructive/10 p-3 text-sm">
              {rowErrors.map((row) => (
                <li
                  key={`${row.line}-${row.message}`}
                  className="text-destructive"
                >
                  <span className="font-medium">Line {row.line}:</span>{' '}
                  {row.message}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="mt-5 flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
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
