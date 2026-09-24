import * as React from 'react'
import { Check, FileText, Landmark, PencilLine } from 'lucide-react'
import {
  Badge,
  Button,
  CurrencyInput,
  DatePicker,
  Field,
  FieldControl,
  FieldLabel,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '#/components/ui'
import { CountryField } from '#/components/settings/country-field'
import { CurrencyField } from '#/components/settings/currency-field'
import { formatMoney, fromIsoDate, toIsoDate, toNumber } from '#/lib/format'
import { serverErrorMessage } from '#/lib/form-errors'
import type { InvoiceDetailRead, InvoiceUpdate, VendorRead } from '#/lib/types'
import { DocumentProcessing } from './document-processing'
import { DocumentTotal } from './document-total'
import { VendorField } from './vendor-field'

export interface VoucherDetailsTabProps {
  invoice: InvoiceDetailRead
  /** Whether the signed-in user holds a management role. Every write on this
   *  tab — correcting the header, verifying it, retriggering the document — is
   *  management-gated server-side; this is what keeps the UI from offering an
   *  action that would be refused. */
  canManage: boolean
  /** The organization's suppliers, for the vendor picker. Null while loading;
   *  the picker degrades to read-only text rather than an empty list. */
  vendors: Array<VendorRead> | null
  /** `POST /invoices/{id}/reprocess`. */
  onReprocess: (invoiceId: string) => Promise<void>
  /** Save a header correction (`PATCH /invoices/{id}`). */
  onUpdateHeader: (invoiceId: string, changes: InvoiceUpdate) => Promise<void>
  /** Verify the header, applying any pending edits first
   *  (`POST /invoices/{id}/verify`). */
  onVerifyHeader: (invoiceId: string, changes: InvoiceUpdate) => Promise<void>
  /** Whether the header editor currently has edits not yet saved. Omit to
   *  ignore — a caller that does not guard drawer dismissal has no use for it. */
  onHeaderDirtyChange?: (dirty: boolean) => void
}

/**
 * Where an invoice's header came from — always shown, and always as text plus
 * an icon, never as a colour alone.
 *
 * It no longer decides what may be edited. It still tells the reviewer how much
 * to trust what they are reading, which is a different and still useful thing:
 * a figure the ERP posted has a bookkeeper behind it, and one the AI parsed has
 * a model behind it.
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
 * A header value shown to someone who may not change it: flat text on a tinted
 * surface, never a disabled input, which still reads as tappable and claims a
 * permission that will never be granted.
 */
/**
 * The ERP's own invoice number, as metadata rather than as a field.
 *
 * It is evidence, not the supplier's number: Billy's `suppliersInvoiceNo` is
 * user-entered and often null and `voucherNo` is blank at least as often, so
 * the connector falls back to the *bill id*. Presenting that in a box labelled
 * "Invoice number" invited a reviewer to reconcile against an internal
 * identifier. The number printed on the document is the editable one; this sits
 * beside the heading, labelled for what it is, and is never edited here —
 * correcting it would put our record out of step with the ERP's while
 * presenting no evidence that it had been.
 */
function PostedNumber({ invoice }: { invoice: InvoiceDetailRead }) {
  if (!invoice.invoice_number) return null
  return (
    <p className="text-xs text-muted-foreground">
      ERP reference{' '}
      <span className="font-medium tabular-nums text-foreground/80">
        {invoice.invoice_number}
      </span>
    </p>
  )
}

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

/**
 * Marks a supplier value a human corrected for this invoice.
 *
 * Worth the pixels because the correction is *invisible* otherwise: the field
 * shows a country, and nothing about it says whether that country came from the
 * supplier catalog or from someone overriding it here. The tooltip carries the
 * catalog's value so the disagreement is one hover away rather than lost.
 */
function OverrideMark({ catalogValue }: { catalogValue: string | null }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700 dark:text-amber-400">
            <PencilLine className="size-3" aria-hidden="true" />
            Corrected
          </span>
        }
      />
      <TooltipContent>
        {catalogValue
          ? `The supplier catalog says “${catalogValue}”. This correction applies to this invoice only.`
          : 'The supplier catalog states nothing here. This correction applies to this invoice only.'}
      </TooltipContent>
    </Tooltip>
  )
}

interface HeaderValues {
  /** The number printed on the scan — the one a human reconciles against, and
   *  the one this form edits. The ERP's as-posted `invoice_number` is shown as
   *  metadata beside it and is not part of this form. */
  document_invoice_number: string
  invoice_date: string
  currency: string
  /** Parsed, not the text in the box. `Number('1,5')` is NaN, which serializes
   *  to a JSON null the API reads as "clear this field" — so a European decimal
   *  silently erased the total. */
  total: number | null
  tax: number | null
  vendor_id: string
  supplier_name: string
  supplier_country_code: string
  supplier_vat_number: string
}

const TEXT_FIELDS = [
  'document_invoice_number',
  'invoice_date',
  'currency',
  'vendor_id',
  'supplier_name',
  'supplier_country_code',
  'supplier_vat_number',
] as const

const NUMBER_FIELDS = ['total', 'tax'] as const

function headerValuesFrom(invoice: InvoiceDetailRead): HeaderValues {
  const text = (value: string | null) => value ?? ''
  const money = (value: InvoiceDetailRead['total']) => {
    if (value === null || value === undefined) return null
    const parsed = toNumber(value)
    return Number.isNaN(parsed) ? null : parsed
  }
  return {
    // Never seeded from `invoice_number`: an empty printed number means the
    // document stated none, and backfilling the ERP's value here would present
    // a bill id as the supplier's own number and invite a reviewer to confirm it.
    document_invoice_number: text(invoice.document_invoice_number),
    invoice_date: text(invoice.invoice_date),
    currency: text(invoice.currency),
    total: money(invoice.total),
    tax: money(invoice.tax),
    vendor_id: text(invoice.vendor_id),
    // The *resolved* supplier, which is the override when there is one and the
    // catalog's value otherwise. Seeding the box with the resolved value means
    // a reviewer correcting one field does not silently blank the other two.
    supplier_name: text(invoice.supplier_name),
    supplier_country_code: text(invoice.supplier_country_code),
    supplier_vat_number: text(invoice.supplier_vat_number),
  }
}

/** Only the fields that changed, empty strings turned back into `null` (a
 *  field the user cleared) — never the whole form, which would send back
 *  fields nobody touched and mark them all as settled. */
function toInvoiceUpdate(current: HeaderValues, original: HeaderValues): InvoiceUpdate {
  const changes: InvoiceUpdate = {}
  for (const field of TEXT_FIELDS) {
    if (current[field] !== original[field]) changes[field] = current[field] || null
  }
  for (const field of NUMBER_FIELDS) {
    // Already a number or null — nothing to parse, so nothing to misparse.
    if (current[field] !== original[field]) changes[field] = current[field]
  }
  return changes
}

function isDirty(current: HeaderValues, original: HeaderValues): boolean {
  return [...TEXT_FIELDS, ...NUMBER_FIELDS].some((f) => current[f] !== original[f])
}

/**
 * The correctable header fields.
 *
 * Rendered by the parent with `key={invoice.id}` — the same discipline
 * `LineEditor` uses for its own local edit state: a *different* invoice
 * is a different identity, not a prop update to react to, so a key forces a
 * remount and a fresh `useState` initializer rather than carrying edit state
 * from the previous invoice forward. A `useEffect` that resets state on prop
 * change would work too, but only after an extra render showing the stale
 * value — the key avoids that render entirely.
 */
function EditableInvoiceHeader({
  invoice,
  vendors,
  onSave,
  onVerify,
  onDirtyChange,
}: {
  invoice: InvoiceDetailRead
  vendors: Array<VendorRead> | null
  onSave: (changes: InvoiceUpdate) => Promise<void>
  onVerify: (changes: InvoiceUpdate) => Promise<void>
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

  const dirty = isDirty(header, original)

  // Reported up so the drawer can guard dismissal — and cleared on unmount
  // (a different invoice, or the panel closing) so a discarded or abandoned
  // edit never leaves a stale "unsaved" flag behind for the next voucher.
  React.useEffect(() => {
    onDirtyChange?.(dirty)
    return () => onDirtyChange?.(false)
  }, [dirty, onDirtyChange])

  function set<K extends keyof HeaderValues>(field: K, value: HeaderValues[K]) {
    setHeader((current) => ({ ...current, [field]: value }))
  }

  function handleCancel() {
    setHeader(original)
    setError(null)
  }

  async function submit(action: (changes: InvoiceUpdate) => Promise<void>) {
    setSubmitting(true)
    setError(null)
    try {
      await action(toInvoiceUpdate(header, original))
      setOriginal(header)
    } catch (failure) {
      setError(serverErrorMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  const overridden = new Set(invoice.supplier_overrides)

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field>
          {/* The number printed on the document. The ERP's own is metadata
              above — frequently a bill id rather than an invoice number at all,
              which is why this is the one a reviewer corrects. */}
          <FieldLabel>Invoice number</FieldLabel>
          <FieldControl
            value={header.document_invoice_number}
            placeholder="As printed on the document"
            onChange={(event) => set('document_invoice_number', event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel>Invoice date</FieldLabel>
          {/* A calendar, not free text. `toIsoDate` builds the string from the
              local date parts: `toISOString()` converts through UTC first, so a
              date picked as the 1st in Copenhagen would submit the 31st — and
              only for viewers behind UTC. */}
          <DatePicker
            aria-label="Invoice date"
            value={fromIsoDate(header.invoice_date)}
            onChange={(date) => set('invoice_date', toIsoDate(date) ?? '')}
          />
        </Field>
        <Field>
          <FieldLabel>Currency</FieldLabel>
          {/* A closed set of ISO 4217 codes, the same picker Settings uses —
              not a text box a typo fits through. The money fields below format
              against whatever is chosen here, so the two cannot disagree. */}
          <CurrencyField
            aria-label="Currency"
            value={header.currency}
            onChange={(code) => set('currency', code)}
          />
        </Field>
        <Field>
          <FieldLabel>Total</FieldLabel>
          <CurrencyInput
            aria-label="Total"
            currency={header.currency || null}
            value={header.total}
            onChange={(value) => set('total', value)}
          />
        </Field>
        <Field>
          <FieldLabel>Tax</FieldLabel>
          <CurrencyInput
            aria-label="Tax"
            currency={header.currency || null}
            value={header.tax}
            onChange={(value) => set('tax', value)}
          />
        </Field>
      </div>

      <section className="flex flex-col gap-3 rounded-md border border-border/60 p-3">
        <div className="flex flex-col gap-0.5">
          <h4 className="text-sm font-semibold text-foreground">Supplier</h4>
          {/* Stated rather than implied: the supplier catalog is shared, and a
              reviewer who thinks they are fixing it everywhere would be wrong. */}
          <p className="text-xs text-muted-foreground">
            Picking a different supplier re-points this invoice. Correcting the name,
            country or VAT number below applies to this invoice only — the supplier
            record itself is left alone.
          </p>
        </div>

        <Field>
          <FieldLabel>Supplier</FieldLabel>
          <VendorField
            value={header.vendor_id}
            vendors={vendors}
            onChange={(vendorId) => set('vendor_id', vendorId)}
          />
        </Field>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field>
            <FieldLabel>
              Name
              {overridden.has('supplier_name') ? <OverrideMark catalogValue={null} /> : null}
            </FieldLabel>
            <FieldControl
              value={header.supplier_name}
              onChange={(event) => set('supplier_name', event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>
              VAT number
              {overridden.has('supplier_vat_number') ? <OverrideMark catalogValue={null} /> : null}
            </FieldLabel>
            <FieldControl
              value={header.supplier_vat_number}
              onChange={(event) => set('supplier_vat_number', event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>
              Country
              {overridden.has('supplier_country_code') ? (
                <OverrideMark catalogValue={null} />
              ) : null}
            </FieldLabel>
            {/* A closed set of ISO codes, so the same combobox Settings uses
                rather than a text box a typo fits through. */}
            <CountryField
              value={header.supplier_country_code}
              onChange={(code) => set('supplier_country_code', code)}
            />
          </Field>
        </div>
      </section>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={submitting || !dirty} onClick={() => void submit(onSave)}>
          {submitting ? 'Saving…' : 'Save'}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={submitting || !dirty}
          onClick={handleCancel}
        >
          Cancel
        </Button>
        {/* Available whether or not anything was edited: accepting the parsed
            values unchanged is itself the signal — "I read these and they are
            right" — and it is the one a correction cannot express. */}
        <Button
          size="sm"
          variant="outline"
          disabled={submitting}
          onClick={() => void submit(onVerify)}
        >
          <Check aria-hidden="true" />
          {dirty ? 'Save and verify' : 'Verify header'}
        </Button>
      </div>
    </div>
  )
}

/** Who verified this header and when, once someone has. */
function VerifiedNote({ invoice }: { invoice: InvoiceDetailRead }) {
  if (invoice.verified_at === null) return null
  const when = new Date(invoice.verified_at)
  return (
    <p className="text-xs text-muted-foreground">
      Verified {Number.isNaN(when.getTime()) ? invoice.verified_at : when.toLocaleString()}
      {invoice.verified_by ? ` by ${invoice.verified_by}` : ''}
      {invoice.verified_fields.length > 0
        ? ` — ${invoice.verified_fields.join(', ')} will not be overwritten by a sync`
        : ''}
    </p>
  )
}

/**
 * The Details tab: the invoice header, and where its lines came from.
 *
 * Every parsed field here is correctable by a management role, whatever the
 * invoice's provenance. It used to be gated on `source === 'pdf_extraction'`,
 * which no production invoice ever was — so the editor existed and no customer
 * could reach it. What decides the affordance now is the reader's *role*: a
 * `viewer` sees the same values as flat evidence text, never a disabled input.
 */
export function VoucherDetailsTab({
  invoice,
  canManage,
  vendors,
  onReprocess,
  onUpdateHeader,
  onVerifyHeader,
  onHeaderDirtyChange,
}: VoucherDetailsTabProps) {
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex flex-col gap-0.5">
            <h3 className="text-sm font-semibold text-foreground">Invoice header</h3>
            <PostedNumber invoice={invoice} />
          </div>
          <ProvenanceBadge source={invoice.source} />
        </div>

        {/* Above the header rather than beside the Total field, so it reads the
            same to a manager (who sees inputs) and a viewer (who sees evidence
            text). The disagreement is about the invoice, not about one input. */}
        <DocumentTotal invoice={invoice} />

        {canManage ? (
          <EditableInvoiceHeader
            key={invoice.id}
            invoice={invoice}
            vendors={vendors}
            onSave={(changes) => onUpdateHeader(invoice.id, changes)}
            onVerify={(changes) => onVerifyHeader(invoice.id, changes)}
            onDirtyChange={onHeaderDirtyChange}
          />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <ReadOnlyField label="Invoice number" value={invoice.document_invoice_number} />
            <ReadOnlyField label="Invoice date" value={invoice.invoice_date} />
            <ReadOnlyField
              label="Total"
              value={invoice.total !== null ? formatMoney(invoice.total, invoice.currency) : null}
            />
            <ReadOnlyField
              label="Tax"
              value={invoice.tax !== null ? formatMoney(invoice.tax, invoice.currency) : null}
            />
            <ReadOnlyField label="Supplier" value={invoice.supplier_name} />
            <ReadOnlyField label="Supplier country" value={invoice.supplier_country_code} />
            <ReadOnlyField label="Supplier VAT number" value={invoice.supplier_vat_number} />
          </div>
        )}

        <VerifiedNote invoice={invoice} />
      </section>

      {/* The lines moved to their own tab — they are the unit this product
          works in, and the only thing on the voucher a human corrects. What
          stays here is the header and where its lines came from. */}
      <DocumentProcessing
        invoice={invoice}
        canRetrigger={canManage}
        onReprocess={onReprocess}
      />
    </div>
  )
}
