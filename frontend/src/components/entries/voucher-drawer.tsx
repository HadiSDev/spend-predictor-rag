import * as React from 'react'
import { ChevronLeft, FileText } from 'lucide-react'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  Skeleton,
  Tabs,
  TabsList,
  TabsPanel,
  TabsTab,
  cn,
} from '#/components/ui'
import { formatMoney } from '#/lib/format'
import type { ErpEntryRead, VoucherAuditRead, VoucherDetailRead, VoucherTab } from '#/lib/types'
import { InvoiceDocument } from './invoice-document'
import type { LineCorrections } from './line-category-editor'
import { VoucherActivityTab } from './voucher-activity-tab'
import { VoucherDetailsTab } from './voucher-details-tab'
import { VoucherPostingsTab } from './voucher-postings-tab'

export interface VoucherDrawerProps {
  /** `undefined` while the detail request is in flight — never an empty object. */
  detail: VoucherDetailRead | undefined
  loading: boolean
  /** Newest-first, exactly as the API returns it — passed straight through. */
  auditRows: Array<VoucherAuditRead>
  auditLoading: boolean
  /** Controlled so the owner (Task 14) can keep it in the URL. */
  tab: VoucherTab
  open: boolean
  onTabChange: (tab: VoucherTab) => void
  onOpenChange: (open: boolean) => void
  onVerifyLine: (lineId: string, corrections: LineCorrections) => Promise<void>
  /** True while the Details tab has edits not yet accepted. Dismissing while
   *  true asks for confirmation instead of closing outright. */
  hasUnsavedChanges: boolean
}

/** The supplier, when every posting on the voucher agrees on one; `null` when
 *  there is no vendor or the postings disagree — never a guess. */
function voucherVendor(entries: Array<ErpEntryRead>): string | null {
  const names = new Set(entries.map((entry) => entry.vendor_name).filter((name): name is string => Boolean(name)))
  return names.size === 1 ? [...names][0] : null
}

function VoucherHeader({ detail }: { detail: VoucherDetailRead }) {
  const vendor = voucherVendor(detail.entries)
  const postingsLabel = `${detail.entry_count} posting${detail.entry_count === 1 ? '' : 's'}`
  // `amount`/`currency` come straight off the payload — computed server-side
  // by the same rule `/erp-entries/vouchers` uses, so this figure always
  // agrees with the table row the drawer was opened from. Never recomputed
  // here: two implementations of "what a voucher totals" is how they drift.
  const totalLabel =
    detail.amount !== null
      ? formatMoney(detail.amount, detail.currency)
      : detail.currency === null
        ? 'Mixed currencies'
        : '—'

  return (
    <DrawerHeader>
      <DrawerTitle>{detail.voucher_id ?? 'No voucher'}</DrawerTitle>
      <DrawerDescription className="flex flex-wrap items-center gap-x-1.5">
        <span>{vendor ?? '—'}</span>
        <span aria-hidden="true">·</span>
        <span>{detail.accounting_date ?? '—'}</span>
        <span aria-hidden="true">·</span>
        <span>{postingsLabel}</span>
        <span aria-hidden="true">·</span>
        <span>{totalLabel}</span>
      </DrawerDescription>
    </DrawerHeader>
  )
}

function DrawerLoading() {
  return (
    <div className="flex flex-col gap-3">
      <Skeleton className="h-6 w-48 rounded-md" />
      <Skeleton className="h-4 w-64 rounded-md" />
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-10 rounded-md" />
      ))}
    </div>
  )
}

/**
 * The voucher-wide detail panel: PDF beside the tabbed detail when the
 * voucher has an invoice, a plain Postings/Activity panel when it does not
 * (the common case — a journal entry has nothing to review). Presentational:
 * every value and callback arrives as a prop, so it renders directly in a
 * test with no router or query client.
 */
export function VoucherDrawer({
  detail,
  loading,
  auditRows,
  auditLoading,
  tab,
  open,
  onTabChange,
  onOpenChange,
  onVerifyLine,
  hasUnsavedChanges,
}: VoucherDrawerProps) {
  // Which pane a narrow (< lg) viewport is showing — the PDF has no room
  // beside the tabs there, so it becomes a view the tab strip's own "View
  // document" control swaps to, rather than a fourth entry in `VoucherTab`
  // (that type is shared with the URL and stays three-valued).
  const [showDocument, setShowDocument] = React.useState(false)
  const [confirmOpen, setConfirmOpen] = React.useState(false)

  const invoice = detail?.invoice ?? null
  const hasInvoice = invoice !== null

  // A voucher with no invoice has no Details tab at all — not a disabled one.
  // If the controlled `tab` names a tab that does not exist for this voucher
  // (most often `details` on a journal-only voucher), fall back to the first
  // tab that does rather than rendering an empty panel.
  const availableTabs: Array<VoucherTab> = hasInvoice ? ['details', 'postings', 'activity'] : ['postings', 'activity']
  const activeTab: VoucherTab = availableTabs.includes(tab) ? tab : availableTabs[0]

  function handleOpenChange(next: boolean) {
    if (!next && hasUnsavedChanges) {
      setConfirmOpen(true)
      return
    }
    onOpenChange(next)
  }

  function handleDiscard() {
    setConfirmOpen(false)
    onOpenChange(false)
  }

  const ready = detail !== undefined && !loading

  return (
    <>
      <Drawer open={open} onOpenChange={handleOpenChange}>
        <DrawerContent
          side="right"
          size={hasInvoice ? 'wide' : 'default'}
          aria-label="Voucher detail"
          // The popup itself never scrolls — each pane below scrolls on its
          // own, so the header and tab strip stay put.
          className="overflow-hidden"
        >
          {!ready ? (
            <DrawerLoading />
          ) : (
            <>
              <VoucherHeader detail={detail} />
              <div className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row lg:gap-6">
                {invoice ? (
                  <div
                    className={cn(
                      'min-h-0 flex-col lg:flex lg:w-[43%] lg:shrink-0 lg:border-r lg:border-border lg:pr-6',
                      showDocument ? 'flex' : 'hidden lg:flex',
                    )}
                  >
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mb-2 self-start lg:hidden"
                      onClick={() => setShowDocument(false)}
                    >
                      <ChevronLeft aria-hidden="true" />
                      Back to details
                    </Button>
                    <div className="min-h-0 flex-1">
                      <InvoiceDocument invoiceId={invoice.id} filename={detail.document?.filename ?? null} />
                    </div>
                  </div>
                ) : null}

                <div
                  className={cn(
                    'flex min-h-0 flex-1 flex-col',
                    invoice && showDocument ? 'hidden lg:flex' : 'flex',
                  )}
                >
                  {invoice ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      className="mb-3 self-start lg:hidden"
                      onClick={() => setShowDocument(true)}
                    >
                      <FileText aria-hidden="true" />
                      View document
                    </Button>
                  ) : null}

                  <Tabs
                    value={activeTab}
                    onValueChange={(value) => onTabChange(value as VoucherTab)}
                    className="flex min-h-0 flex-1 flex-col gap-3"
                  >
                    <TabsList>
                      {invoice ? <TabsTab value="details">Details</TabsTab> : null}
                      <TabsTab value="postings">Postings</TabsTab>
                      <TabsTab value="activity">Activity</TabsTab>
                    </TabsList>
                    <div className="min-h-0 flex-1 overflow-y-auto">
                      {invoice ? (
                        <TabsPanel value="details" className="ep-tab-fade">
                          <VoucherDetailsTab invoice={invoice} onVerifyLine={onVerifyLine} />
                        </TabsPanel>
                      ) : null}
                      <TabsPanel value="postings" className="ep-tab-fade">
                        <VoucherPostingsTab entries={detail.entries} />
                      </TabsPanel>
                      <TabsPanel value="activity" className="ep-tab-fade">
                        <VoucherActivityTab rows={auditRows} loading={auditLoading} />
                      </TabsPanel>
                    </div>
                  </Tabs>
                </div>
              </div>
            </>
          )}
        </DrawerContent>
      </Drawer>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard unsaved changes?</AlertDialogTitle>
            <AlertDialogDescription>
              This voucher has categorization edits that haven&apos;t been accepted yet. Closing
              now discards them.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              Keep editing
            </Button>
            <Button variant="destructive" onClick={handleDiscard}>
              Discard changes
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
