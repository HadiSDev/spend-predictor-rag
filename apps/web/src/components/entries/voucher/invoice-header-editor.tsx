import * as React from 'react'
import { Check, PencilLine } from 'lucide-react'
import {
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
import { CountryField } from '#/components/fields/country-field'
import { CurrencyField } from '#/components/fields/currency-field'
import { fromIsoDate, toIsoDate } from '#/lib/format/format'
import { serverErrorMessage } from '#/lib/form-errors'
import type {
  InvoiceDetailRead,
  InvoiceUpdate,
  VendorRead,
} from '#/lib/api/types'
import { VendorField } from './vendor-field'
import {
  headerValuesFrom,
  isDirty,
  toInvoiceUpdate,
} from './invoice-header-values'
import type { HeaderValues } from './invoice-header-values'

/** Marks a supplier value a human corrected for this invoice. */
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

/** The correctable header fields. */
export function EditableInvoiceHeader({
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
  const [original, setOriginal] = React.useState<HeaderValues>(() =>
    headerValuesFrom(invoice),
  )
  const [header, setHeader] = React.useState<HeaderValues>(original)
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const dirty = isDirty(header, original)

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
          <FieldLabel>Invoice number</FieldLabel>
          <FieldControl
            value={header.document_invoice_number}
            placeholder="As printed on the document"
            onChange={(event) =>
              set('document_invoice_number', event.target.value)
            }
          />
        </Field>
        <Field>
          <FieldLabel>Invoice date</FieldLabel>
          <DatePicker
            aria-label="Invoice date"
            value={fromIsoDate(header.invoice_date)}
            onChange={(date) => set('invoice_date', toIsoDate(date) ?? '')}
          />
        </Field>
        <Field>
          <FieldLabel>Currency</FieldLabel>
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
          <p className="text-xs text-muted-foreground">
            Picking a different supplier re-points this invoice. Correcting the
            name, country or VAT number below applies to this invoice only — the
            supplier record itself is left alone.
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
              {overridden.has('supplier_name') ? (
                <OverrideMark catalogValue={null} />
              ) : null}
            </FieldLabel>
            <FieldControl
              value={header.supplier_name}
              onChange={(event) => set('supplier_name', event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>
              VAT number
              {overridden.has('supplier_vat_number') ? (
                <OverrideMark catalogValue={null} />
              ) : null}
            </FieldLabel>
            <FieldControl
              value={header.supplier_vat_number}
              onChange={(event) =>
                set('supplier_vat_number', event.target.value)
              }
            />
          </Field>
          <Field>
            <FieldLabel>
              Country
              {overridden.has('supplier_country_code') ? (
                <OverrideMark catalogValue={null} />
              ) : null}
            </FieldLabel>
            <CountryField
              value={header.supplier_country_code}
              onChange={(code) => set('supplier_country_code', code)}
            />
          </Field>
        </div>
      </section>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          disabled={submitting || !dirty}
          onClick={() => void submit(onSave)}
        >
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
