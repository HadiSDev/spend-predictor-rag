import * as React from 'react'
import {
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  Field,
  FieldControl,
  FieldLabel,
} from '#/components/ui'

export interface NodeValues {
  name: string
  code?: string | null
  description?: string | null
}

export function NodeDialog({
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
      await onSubmit({
        name,
        code: code || null,
        description: description || null,
      })
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
            <FieldControl
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Code (optional)</FieldLabel>
            <FieldControl
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
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
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            disabled={busy || name.trim().length === 0}
            onClick={() => void submit()}
          >
            {busy ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
