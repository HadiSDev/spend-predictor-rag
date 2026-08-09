import * as React from 'react'
import { FileText, Landmark } from 'lucide-react'
import { Badge, Field, FieldControl, FieldLabel } from '#/components/ui'
import { formatMoney } from '#/lib/format'
import type { InvoiceDetailRead } from '#/lib/types'
import { LineCategoryEditor } from './line-category-editor'
import type { LineCorrections } from './line-category-editor'

export interface VoucherDetailsTabProps {
  invoice: InvoiceDetailRead
  /** Sending an empty corrections object accepts the AI result as-is. */
  onVerifyLine: (lineId: string, corrections: LineCorrections) => Promise<void>
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

/**
 * The Details tab: the invoice header and the per-line categorization
 * editors. Provenance decides affordance throughout — an ERP-posted header is
 * evidence (flat text, tinted surface); a PDF-parsed header is correctable
 * (real, focusable inputs). Line categorization is AI-produced and always
 * correctable, regardless of the header's source.
 */
export function VoucherDetailsTab({ invoice, onVerifyLine }: VoucherDetailsTabProps) {
  const isErp = invoice.source === 'erp'
  const [header, setHeader] = React.useState<HeaderValues>(() => headerValuesFrom(invoice))

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
                onChange={(event) =>
                  setHeader((current) => ({ ...current, total: event.target.value }))
                }
              />
            </Field>
            <Field>
              <FieldLabel>Tax</FieldLabel>
              <FieldControl
                value={header.tax}
                onChange={(event) =>
                  setHeader((current) => ({ ...current, tax: event.target.value }))
                }
              />
            </Field>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-foreground">Lines</h3>
        {invoice.lines.length === 0 ? (
          <p className="text-sm text-muted-foreground">No lines on this invoice.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {invoice.lines.map((line) => (
              <LineCategoryEditor
                key={line.id}
                line={line}
                currency={invoice.currency}
                onVerify={onVerifyLine}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
