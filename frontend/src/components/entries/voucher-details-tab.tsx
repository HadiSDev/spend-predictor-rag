import * as React from 'react'
import { FileText, Landmark } from 'lucide-react'
import { Badge, Button, Field, FieldControl, FieldLabel } from '#/components/ui'
import { formatMoney } from '#/lib/format'
import { serverErrorMessage } from '#/lib/form-errors'
import type { InvoiceDetailRead, InvoiceUpdate } from '#/lib/types'
import { DocumentProcessing } from './document-processing'

export interface VoucherDetailsTabProps {
  invoice: InvoiceDetailRead
  /** Whether the signed-in user may retrigger document processing — the
   *  endpoint is management-only. */
  canRetrigger: boolean
  /** `POST /invoices/{id}/reprocess`. */
  onReprocess: (invoiceId: string) => Promise<void>
  /** Save a header correction (`PATCH /invoices/{id}`). Only called for a
   *  `pdf_extraction` invoice — the only source this tab ever renders inputs
   *  for; an `erp`-sourced one always shows `ReadOnlyField`s instead. */
  onUpdateHeader: (invoiceId: string, changes: InvoiceUpdate) => Promise<void>
  /** Whether the header editor currently has edits not yet saved. Omit to
   *  ignore — a caller that does not guard drawer dismissal has no use for it. */
  onHeaderDirtyChange?: (dirty: boolean) => void
}

/**
 * Where an invoice's header came from — always shown, and always as text plus
 * an icon, never as a colour alone.
 */
function ProvenanceBadge({ source }: { source: string }) {
  const fromErp = source === 'erp'
  return (
    <Badge
      variant={fromErp ? 'info' : 'outline'}
      title={fromErp ? 'Posted by the ERP' : 'Extracted from the invoice PDF'}
    >
      {fromErp ? <Landmark aria-hidden="true" /> : <FileText aria-hidden="true" />}
      {fromErp ? 'ERP posting' : 'PDF extraction'}
    </Badge>
  )
}

/**
 * A header value posted by the ERP: evidence, rendered as flat text on a
 * tinted surface — never a disabled input, which still reads as tappable.
 */
function ReadOnlyField({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 rounded-md bg-muted/60 px-3 py-2">
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="text-sm text-foreground">
        {value === null || value === undefined || value === '' ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          value
        )}
      </span>
    </div>
  )
}

interface HeaderValues {
  invoice_number: string
  invoice_date: string
  total: string
  tax: string
}

function headerValuesFrom(invoice: InvoiceDetailRead): HeaderValues {
  return {
    invoice_number: invoice.invoice_number ?? '',
    invoice_date: invoice.invoice_date ?? '',
    total: invoice.total === null ? '' : String(invoice.total),
    tax: invoice.tax === null ? '' : String(invoice.tax),
  }
}

/** Only the fields that changed, empty strings turned back into `null` (a
 *  field the user cleared) — never the whole form, which would send back
 *  fields nobody touched. */
function toInvoiceUpdate(current: HeaderValues, original: HeaderValues): InvoiceUpdate {
  const changes: InvoiceUpdate = {}
  if (current.invoice_number !== original.invoice_number) {
    changes.invoice_number = current.invoice_number || null
  }
  if (current.invoice_date !== original.invoice_date) {
    changes.invoice_date = current.invoice_date || null
  }
  if (current.total !== original.total) {
    changes.total = current.total === '' ? null : Number(current.total)
  }
  if (current.tax !== original.tax) {
    changes.tax = current.tax === '' ? null : Number(current.tax)
  }
  return changes
}

/**
 * The correctable (`pdf_extraction`) header fields. Rendered by the parent
 * with `key={invoice.id}` — the same discipline `LineCategoryEditor` uses for
 * its own local edit state: a *different* invoice is a different identity,
 * not a prop update to react to, so a key forces a remount and a fresh
 * `useState` initializer rather than carrying edit state from the previous
 * invoice forward. A `useEffect` that resets state on prop change would work
 * too, but only after an extra render showing the stale value — the key
 * avoids that render entirely.
 */
function EditableInvoiceHeader({
  invoice,
  onSave,
  onDirtyChange,
}: {
  invoice: InvoiceDetailRead
  onSave: (changes: InvoiceUpdate) => Promise<void>
  onDirtyChange?: (dirty: boolean) => void
}) {
  // The saved baseline is state, not recomputed from `invoice` every render:
  // a successful save updates it immediately (below), so "dirty" clears the
  // instant the save resolves rather than waiting on the detail query to
  // refetch and flow a new `invoice` prop back down.
  const [original, setOriginal] = React.useState<HeaderValues>(() => headerValuesFrom(invoice))
  const [header, setHeader] = React.useState<HeaderValues>(original)
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const dirty =
    header.invoice_number !== original.invoice_number ||
    header.invoice_date !== original.invoice_date ||
    header.total !== original.total ||
    header.tax !== original.tax

  // Reported up so the drawer can guard dismissal — and cleared on unmount
  // (a different invoice, or the panel closing) so a discarded or abandoned
  // edit never leaves a stale "unsaved" flag behind for the next voucher.
  React.useEffect(() => {
    onDirtyChange?.(dirty)
    return () => onDirtyChange?.(false)
  }, [dirty, onDirtyChange])

  function handleCancel() {
    setHeader(original)
    setError(null)
  }

  async function handleSave() {
    setSubmitting(true)
    setError(null)
    try {
      await onSave(toInvoiceUpdate(header, original))
      setOriginal(header)
    } catch (failure) {
      setError(serverErrorMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field>
          <FieldLabel>Invoice number</FieldLabel>
          <FieldControl
            value={header.invoice_number}
            onChange={(event) =>
              setHeader((current) => ({ ...current, invoice_number: event.target.value }))
            }
          />
        </Field>
        <Field>
          <FieldLabel>Invoice date</FieldLabel>
          <FieldControl
            value={header.invoice_date}
            onChange={(event) =>
              setHeader((current) => ({ ...current, invoice_date: event.target.value }))
            }
          />
        </Field>
        <Field>
          <FieldLabel>Total</FieldLabel>
          <FieldControl
            value={header.total}
            onChange={(event) => setHeader((current) => ({ ...current, total: event.target.value }))}
          />
        </Field>
        <Field>
          <FieldLabel>Tax</FieldLabel>
          <FieldControl
            value={header.tax}
            onChange={(event) => setHeader((current) => ({ ...current, tax: event.target.value }))}
          />
        </Field>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <div className="flex items-center gap-2">
        <Button size="sm" disabled={submitting || !dirty} onClick={() => void handleSave()}>
          {submitting ? 'Saving…' : 'Save'}
        </Button>
        <Button size="sm" variant="ghost" disabled={submitting || !dirty} onClick={handleCancel}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

/**
 * The Details tab: the invoice header, and where its lines came from.
 *
 * Provenance decides affordance throughout — an ERP-posted header is evidence
 * (flat text, tinted surface); a PDF-parsed header is correctable (real,
 * focusable inputs). The lines themselves live on their own tab now: they are
 * the unit this product works in, not a footnote to a header nobody edits.
 */
export function VoucherDetailsTab({
  invoice,
  canRetrigger,
  onReprocess,
  onUpdateHeader,
  onHeaderDirtyChange,
}: VoucherDetailsTabProps) {
  const isErp = invoice.source === 'erp'

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-foreground">Invoice header</h3>
          <ProvenanceBadge source={invoice.source} />
        </div>

        {isErp ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <ReadOnlyField label="Invoice number" value={invoice.invoice_number} />
            <ReadOnlyField label="Invoice date" value={invoice.invoice_date} />
            <ReadOnlyField
              label="Total"
              value={invoice.total !== null ? formatMoney(invoice.total, invoice.currency) : null}
            />
            <ReadOnlyField
              label="Tax"
              value={invoice.tax !== null ? formatMoney(invoice.tax, invoice.currency) : null}
            />
          </div>
        ) : (
          <EditableInvoiceHeader
            key={invoice.id}
            invoice={invoice}
            onSave={(changes) => onUpdateHeader(invoice.id, changes)}
            onDirtyChange={onHeaderDirtyChange}
          />
        )}
      </section>

      {/* The lines moved to their own tab — they are the unit this product
          works in, and the only thing on the voucher a human corrects. What
          stays here is the header and where its lines came from. */}
      <DocumentProcessing
        invoice={invoice}
        canRetrigger={canRetrigger}
        onReprocess={onReprocess}
      />
    </div>
  )
}
