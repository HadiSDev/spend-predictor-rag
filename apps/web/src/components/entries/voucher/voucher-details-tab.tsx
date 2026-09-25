import * as React from 'react'
import { FileText, Landmark } from 'lucide-react'
import { Badge } from '#/components/ui'
import { formatMoney } from '#/lib/format/format'
import type {
  InvoiceDetailRead,
  InvoiceUpdate,
  VendorRead,
} from '#/lib/api/types'
import { DocumentProcessing } from '#/components/entries/invoice-document/document-processing'
import { DocumentTotal } from '#/components/entries/invoice-document/document-total'
import { EditableInvoiceHeader } from './invoice-header-editor'

export interface VoucherDetailsTabProps {
  invoice: InvoiceDetailRead
  /** Whether the signed-in user holds a management role. */
  canManage: boolean
  /** The organization's suppliers, or null while loading. */
  vendors: Array<VendorRead> | null
  /** `POST /invoices/{id}/reprocess`. */
  onReprocess: (invoiceId: string) => Promise<void>
  /** Save a header correction (`PATCH /invoices/{id}`). */
  onUpdateHeader: (invoiceId: string, changes: InvoiceUpdate) => Promise<void>
  /** Verify the header, applying any pending edits first. */
  onVerifyHeader: (invoiceId: string, changes: InvoiceUpdate) => Promise<void>
  /** Whether the header editor has unsaved edits. */
  onHeaderDirtyChange?: (dirty: boolean) => void
}

/** Where an invoice's header came from. */
function ProvenanceBadge({ source }: { source: string }) {
  const fromErp = source === 'erp'
  return (
    <Badge
      variant={fromErp ? 'info' : 'outline'}
      title={fromErp ? 'Posted by the ERP' : 'Extracted from the invoice PDF'}
    >
      {fromErp ? (
        <Landmark aria-hidden="true" />
      ) : (
        <FileText aria-hidden="true" />
      )}
      {fromErp ? 'ERP posting' : 'PDF extraction'}
    </Badge>
  )
}

/** The supplier's invoice number as recorded in the ERP. */
function PostedNumber({ invoice }: { invoice: InvoiceDetailRead }) {
  if (!invoice.invoice_number) {
    return null
  }
  return (
    <p className="text-xs text-muted-foreground">
      Invoice number in the ERP{' '}
      <span className="font-medium tabular-nums text-foreground/80">
        {invoice.invoice_number}
      </span>
    </p>
  )
}

function ReadOnlyField({
  label,
  value,
}: {
  label: string
  value: React.ReactNode
}) {
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

/** Who verified this header and when. */
function VerifiedNote({ invoice }: { invoice: InvoiceDetailRead }) {
  if (invoice.verified_at === null) {
    return null
  }
  const when = new Date(invoice.verified_at)
  return (
    <p className="text-xs text-muted-foreground">
      Verified{' '}
      {Number.isNaN(when.getTime())
        ? invoice.verified_at
        : when.toLocaleString()}
      {invoice.verified_by ? ` by ${invoice.verified_by}` : ''}
      {invoice.verified_fields.length > 0
        ? ` — ${invoice.verified_fields.join(', ')} will not be overwritten by a sync`
        : ''}
    </p>
  )
}

/** The Details tab: the invoice header and where its lines came from. */
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
            <h3 className="text-sm font-semibold text-foreground">
              Invoice header
            </h3>
            <PostedNumber invoice={invoice} />
          </div>
          <ProvenanceBadge source={invoice.source} />
        </div>

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
            <ReadOnlyField
              label="Invoice number"
              value={invoice.document_invoice_number}
            />
            <ReadOnlyField label="Invoice date" value={invoice.invoice_date} />
            <ReadOnlyField
              label="Total"
              value={
                invoice.total !== null
                  ? formatMoney(invoice.total, invoice.currency)
                  : null
              }
            />
            <ReadOnlyField
              label="Tax"
              value={
                invoice.tax !== null
                  ? formatMoney(invoice.tax, invoice.currency)
                  : null
              }
            />
            <ReadOnlyField label="Supplier" value={invoice.supplier_name} />
            <ReadOnlyField
              label="Supplier country"
              value={invoice.supplier_country_code}
            />
            <ReadOnlyField
              label="Supplier VAT number"
              value={invoice.supplier_vat_number}
            />
          </div>
        )}

        <VerifiedNote invoice={invoice} />
      </section>

      <DocumentProcessing
        invoice={invoice}
        canRetrigger={canManage}
        onReprocess={onReprocess}
      />
    </div>
  )
}
