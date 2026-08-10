import type { InvoiceDetailRead, SpendCategoryRead } from '#/lib/types'
import { LineCategoryEditor } from './line-category-editor'
import type { LineCorrections } from './line-category-editor'
import { ProvenanceMark } from './voucher-table'

export interface VoucherLinesTabProps {
  invoice: InvoiceDetailRead
  /** The company's spend tree, flat and shallowest-first. Null while loading;
   *  empty when no tree is assigned. Passed down rather than fetched here so
   *  one request serves every line on the voucher. */
  spendTreeNodes: Array<SpendCategoryRead> | null
  companySettingsHref?: string
  onVerifyLine: (lineId: string, corrections: LineCorrections) => Promise<void>
}

/**
 * The Lines tab: what was bought, and the category assigned to each line.
 *
 * Its own tab rather than a section under Details, because the line is now the
 * unit this product works in — it is what the table lists, what a row opens
 * onto, and the only thing on the voucher a human corrects. Burying it under a
 * header nobody edits made it the second thing on a tab about something else.
 *
 * A stand-in line is marked. Not disabled and not tinted as a problem: it is a
 * real line, categorizable and verifiable like any other, and most vouchers
 * have no scan to do better from. The mark says only that its description is
 * the bookkeeper's memo rather than what was bought — which is exactly what a
 * reader deciding whether to trust the category needs to know.
 */
export function VoucherLinesTab({
  invoice,
  spendTreeNodes,
  companySettingsHref,
  onVerifyLine,
}: VoucherLinesTabProps) {
  if (invoice.lines.length === 0) {
    return <p className="text-sm text-muted-foreground">No lines on this invoice.</p>
  }
  return (
    <div className="flex flex-col gap-3">
      {invoice.lines.map((line) => (
        <div key={line.id} className="flex flex-col gap-1">
          {line.origin === 'entry_fallback' ? (
            <div className="self-start">
              <ProvenanceMark origin={line.origin} />
            </div>
          ) : null}
          <LineCategoryEditor
            line={line}
            currency={invoice.currency}
            nodes={spendTreeNodes}
            companySettingsHref={companySettingsHref}
            onVerify={onVerifyLine}
          />
        </div>
      ))}
    </div>
  )
}
