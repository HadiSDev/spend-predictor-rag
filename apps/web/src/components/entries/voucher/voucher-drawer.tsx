import * as React from 'react'
import { ChevronLeft, FileText, TriangleAlert } from 'lucide-react'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
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
import { formatMoney } from '#/lib/format/format'
import type {
  ErpEntryRead,
  InvoiceLineUpdate,
  InvoiceUpdate,
  SpendCategoryRead,
  VendorRead,
  VoucherAuditRead,
  VoucherDetailRead,
  VoucherTab,
} from '#/lib/api/types'
import { InvoiceDocument } from '#/components/entries/invoice-document/invoice-document'
import type { LineCorrections } from '#/components/entries/lines/line-editor'
import { VoucherActivityTab } from './voucher-activity-tab'
import { VoucherDetailsTab } from './voucher-details-tab'
import { VoucherLinesTab } from './voucher-lines-tab'
import { VoucherPostingsTab } from './voucher-postings-tab'

export interface VoucherDrawerProps {
  /** `undefined` while the detail request is in flight. */
  detail: VoucherDetailRead | undefined
  loading: boolean
  /** Newest first, as returned by the API. */
  auditRows: Array<VoucherAuditRead>
  auditLoading: boolean
  /** The active tab, controlled by the owner. */
  tab: VoucherTab
  open: boolean
  onTabChange: (tab: VoucherTab) => void
  onOpenChange: (open: boolean) => void
  onVerifyLine: (lineId: string, corrections: LineCorrections) => Promise<void>
  /** The company's spend tree, or null while loading. */
  spendTreeNodes: Array<SpendCategoryRead> | null
  /** Where a manager assigns the company's tree. */
  companySettingsHref?: string
  /** Save a header correction on the Details tab. */
  onUpdateHeader: (invoiceId: string, changes: InvoiceUpdate) => Promise<void>
  /** Verify the header, applying any pending edits first. */
  onVerifyHeader: (invoiceId: string, changes: InvoiceUpdate) => Promise<void>
  /** Correct what a line says was bought. */
  onUpdateLine: (lineId: string, changes: InvoiceLineUpdate) => Promise<void>
  /** Add a line to the open invoice. */
  onCreateLine: (invoiceId: string) => Promise<void>
  /** Delete a line from the open invoice. */
  onDeleteLine: (lineId: string) => Promise<void>
  /** The line the Lines tab opens on. */
  initialLineId?: string | null
  /** The organization's suppliers. */
  vendors: Array<VendorRead> | null
  /** Queue the document to be read again. */
  onReprocess: (invoiceId: string) => Promise<void>
  /** Whether the signed-in user holds a management role. */
  canManage: boolean
  /** Whether the Details tab's header editor has unsaved edits. */
  onHeaderDirtyChange?: (dirty: boolean) => void
  /** Whether dismissing must first confirm discarding edits. */
  hasUnsavedChanges: boolean
}

/** The supplier all postings agree on, or `null`. */
function voucherVendor(entries: Array<ErpEntryRead>): string | null {
  const names = new Set(
    entries
      .map((entry) => entry.vendor_name)
      .filter((name): name is string => Boolean(name)),
  )
  return names.size === 1 ? [...names][0] : null
}

function VoucherHeader({ detail }: { detail: VoucherDetailRead }) {
  const vendor = voucherVendor(detail.entries)
  const postingsLabel = `${detail.entry_count} posting${detail.entry_count === 1 ? '' : 's'}`
  const totalLabel =
    detail.amount !== null
      ? formatMoney(detail.amount, detail.currency)
      : detail.currency === null
        ? 'Mixed currencies'
        : '—'

  return (
    <DrawerHeader>
      <DrawerTitle className="flex flex-wrap items-center gap-2">
        {detail.voucher_id ?? 'No voucher'}
        {detail.invoice && !detail.invoice.lines_reconciled ? (
          <Badge variant="warning">
            <TriangleAlert className="size-3" aria-hidden="true" />
            Lines do not add up
          </Badge>
        ) : null}
      </DrawerTitle>
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

/** The voucher-wide detail panel. */
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
  spendTreeNodes,
  companySettingsHref,
  onUpdateHeader,
  onVerifyHeader,
  onUpdateLine,
  onCreateLine,
  onDeleteLine,
  initialLineId,
  vendors,
  onReprocess,
  canManage,
  onHeaderDirtyChange,
  hasUnsavedChanges,
}: VoucherDrawerProps) {
  const [showDocument, setShowDocument] = React.useState(false)
  const [confirmOpen, setConfirmOpen] = React.useState(false)

  const invoice = detail?.invoice ?? null
  const hasInvoice = invoice !== null

  const availableTabs: Array<VoucherTab> = hasInvoice
    ? ['lines', 'details', 'postings', 'activity']
    : ['postings', 'activity']
  const activeTab: VoucherTab = availableTabs.includes(tab)
    ? tab
    : availableTabs[0]

  const ready = detail !== undefined && !loading

  React.useEffect(() => {
    if (ready && activeTab !== tab) {
      onTabChange(activeTab)
    }
  }, [ready, activeTab, tab, onTabChange])

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

  return (
    <>
      <Drawer open={open} onOpenChange={handleOpenChange}>
        <DrawerContent
          side="right"
          size={hasInvoice ? 'wide' : 'default'}
          aria-label="Voucher detail"
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
                      <InvoiceDocument
                        invoiceId={invoice.id}
                        filename={detail.document?.filename ?? null}
                      />
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
                      {invoice ? <TabsTab value="lines">Lines</TabsTab> : null}
                      {invoice ? (
                        <TabsTab value="details">Details</TabsTab>
                      ) : null}
                      <TabsTab value="postings">Postings</TabsTab>
                      <TabsTab value="activity">Activity</TabsTab>
                    </TabsList>
                    <div className="-mx-2 min-h-0 flex-1 overflow-y-auto px-2 pb-2">
                      {invoice ? (
                        <TabsPanel value="lines" className="ep-tab-fade">
                          <VoucherLinesTab
                            invoice={invoice}
                            initialLineId={initialLineId}
                            spendTreeNodes={spendTreeNodes}
                            companySettingsHref={companySettingsHref}
                            canManage={canManage}
                            onVerifyLine={onVerifyLine}
                            onUpdateLine={onUpdateLine}
                            onCreateLine={onCreateLine}
                            onDeleteLine={onDeleteLine}
                          />
                        </TabsPanel>
                      ) : null}
                      {invoice ? (
                        <TabsPanel value="details" className="ep-tab-fade">
                          <VoucherDetailsTab
                            invoice={invoice}
                            canManage={canManage}
                            vendors={vendors}
                            onReprocess={onReprocess}
                            onUpdateHeader={onUpdateHeader}
                            onVerifyHeader={onVerifyHeader}
                            onHeaderDirtyChange={onHeaderDirtyChange}
                          />
                        </TabsPanel>
                      ) : null}
                      <TabsPanel value="postings" className="ep-tab-fade">
                        <VoucherPostingsTab entries={detail.entries} />
                      </TabsPanel>
                      <TabsPanel value="activity" className="ep-tab-fade">
                        <VoucherActivityTab
                          rows={auditRows}
                          loading={auditLoading}
                        />
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
              This voucher has categorization edits that haven&apos;t been
              accepted yet. Closing now discards them.
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
