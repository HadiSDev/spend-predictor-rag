import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { ClientOnly } from '@tanstack/react-router'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileWarning,
  FileX,
  RotateCw,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { Button, IconButton, Skeleton } from '#/components/ui'
import { useApi } from '#/lib/auth/auth'
import { ApiError } from '#/lib/api/api-client'
import { invoiceDocumentQueryOptions } from '#/lib/api/entries'

const LazyViewer = React.lazy(() => import('./invoice-document-viewer'))

/** How a fetched document can be shown, based on its media type. */
type DocumentKind = 'pdf' | 'image' | 'unsupported'

function kindOf(blob: Blob): DocumentKind {
  const type = blob.type.toLowerCase().split(';')[0].trim()
  if (type === 'application/pdf') {
    return 'pdf'
  }
  if (type.startsWith('image/')) {
    return 'image'
  }
  return 'unsupported'
}

const MIN_SCALE = 0.4
const MAX_SCALE = 3
const ZOOM_STEP = 0.2

export interface InvoiceDocumentProps {
  /** The invoice whose scanned document should be shown. */
  invoiceId: string | null
  /** The document's original filename, used for the download control. */
  filename: string | null
}

function NoDocumentState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 rounded-md bg-muted p-8 text-center">
      <FileX className="size-8 text-muted-foreground" aria-hidden="true" />
      <p className="text-sm text-muted-foreground">
        No document attached to this invoice.
      </p>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <Skeleton className="h-10 w-full rounded-md" />
      <Skeleton className="h-full min-h-100 w-full flex-1 rounded-md" />
    </div>
  )
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 rounded-md bg-muted p-8 text-center">
      <FileWarning className="size-8 text-destructive" aria-hidden="true" />
      <p className="max-w-sm text-sm text-muted-foreground">{message}</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        <RotateCw aria-hidden="true" />
        Retry
      </Button>
    </div>
  )
}

function UnsupportedState({
  type,
  onDownload,
}: {
  type: string
  onDownload: () => void
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 rounded-md p-8 text-center">
      <FileWarning
        className="size-8 text-muted-foreground"
        aria-hidden="true"
      />
      <p className="max-w-sm text-sm text-muted-foreground">
        {type
          ? `This document is a ${type} file`
          : 'This document is of an unknown type'}{' '}
        and cannot be previewed here.
      </p>
      <Button variant="secondary" size="sm" onClick={onDownload}>
        <Download aria-hidden="true" />
        Download
      </Button>
    </div>
  )
}

function ViewerSkeleton() {
  return <Skeleton className="mx-auto h-200 w-150 rounded-md" />
}

interface ToolbarProps {
  /** Whether page controls are shown. */
  paginated: boolean
  pageNumber: number
  numPages: number
  scale: number
  onPrev: () => void
  onNext: () => void
  onZoomOut: () => void
  onZoomIn: () => void
  onDownload: () => void
}

/** 44px hit area for icon-only toolbar controls. */
const hitArea = 'size-11'

function Toolbar({
  paginated,
  pageNumber,
  numPages,
  scale,
  onPrev,
  onNext,
  onZoomOut,
  onZoomIn,
  onDownload,
}: ToolbarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-2 py-1.5">
      {!paginated && <span />}
      {paginated && (
        <div className="flex items-center gap-1">
          <IconButton
            aria-label="Previous page"
            className={hitArea}
            disabled={pageNumber <= 1}
            onClick={onPrev}
          >
            <ChevronLeft aria-hidden="true" />
          </IconButton>
          <span className="min-w-26 text-center text-sm tabular-nums text-muted-foreground">
            Page {pageNumber} of {numPages || '—'}
          </span>
          <IconButton
            aria-label="Next page"
            className={hitArea}
            disabled={numPages === 0 || pageNumber >= numPages}
            onClick={onNext}
          >
            <ChevronRight aria-hidden="true" />
          </IconButton>
        </div>
      )}
      <div className="flex items-center gap-1">
        <IconButton
          aria-label="Zoom out"
          className={hitArea}
          disabled={scale <= MIN_SCALE}
          onClick={onZoomOut}
        >
          <ZoomOut aria-hidden="true" />
        </IconButton>
        <span className="min-w-14 text-center text-sm tabular-nums text-muted-foreground">
          {Math.round(scale * 100)}%
        </span>
        <IconButton
          aria-label="Zoom in"
          className={hitArea}
          disabled={scale >= MAX_SCALE}
          onClick={onZoomIn}
        >
          <ZoomIn aria-hidden="true" />
        </IconButton>
        <IconButton
          aria-label="Download document"
          className={hitArea}
          onClick={onDownload}
        >
          <Download aria-hidden="true" />
        </IconButton>
      </div>
    </div>
  )
}

/** Viewer for an invoice's scanned document (PDF or image). */
export function InvoiceDocument({ invoiceId, filename }: InvoiceDocumentProps) {
  const api = useApi()
  const query = useQuery(invoiceDocumentQueryOptions(api, invoiceId))

  const [objectUrl, setObjectUrl] = React.useState<string | null>(null)
  const [numPages, setNumPages] = React.useState(0)
  const [pageNumber, setPageNumber] = React.useState(1)
  const [scale, setScale] = React.useState(1)
  const [renderError, setRenderError] = React.useState<string | null>(null)

  React.useEffect(() => {
    const blob = query.data
    if (!blob) {
      return
    }
    const url = URL.createObjectURL(blob)
    setObjectUrl(url)
    setNumPages(0)
    setPageNumber(1)
    setRenderError(null)
    return () => {
      URL.revokeObjectURL(url)
    }
  }, [query.data])

  if (invoiceId === null) {
    return <NoDocumentState />
  }

  if (query.isPending) {
    return <LoadingState />
  }

  if (query.isError) {
    const message =
      query.error instanceof ApiError
        ? query.error.detail
        : 'Could not load the document.'
    return <ErrorState message={message} onRetry={() => query.refetch()} />
  }

  if (renderError) {
    return <ErrorState message={renderError} onRetry={() => query.refetch()} />
  }

  const blob = query.data
  if (!objectUrl || !blob) {
    return <LoadingState />
  }

  const kind = kindOf(blob)

  const handleDownload = () => {
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = filename ?? 'document'
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {kind !== 'unsupported' && (
        <Toolbar
          paginated={kind === 'pdf'}
          pageNumber={pageNumber}
          numPages={numPages}
          scale={scale}
          onPrev={() => setPageNumber((p) => Math.max(1, p - 1))}
          onNext={() => setPageNumber((p) => Math.min(numPages || 1, p + 1))}
          onZoomOut={() =>
            setScale((s) =>
              Math.max(MIN_SCALE, Number((s - ZOOM_STEP).toFixed(2))),
            )
          }
          onZoomIn={() =>
            setScale((s) =>
              Math.min(MAX_SCALE, Number((s + ZOOM_STEP).toFixed(2))),
            )
          }
          onDownload={handleDownload}
        />
      )}
      <div className="min-h-0 flex-1 overflow-auto bg-muted p-4">
        {kind === 'pdf' && (
          <ClientOnly fallback={<ViewerSkeleton />}>
            <React.Suspense fallback={<ViewerSkeleton />}>
              <LazyViewer
                url={objectUrl}
                scale={scale}
                pageNumber={pageNumber}
                onDocumentLoad={setNumPages}
                onDocumentError={setRenderError}
              />
            </React.Suspense>
          </ClientOnly>
        )}
        {kind === 'image' && (
          <img
            src={objectUrl}
            alt={filename ?? 'Scanned invoice document'}
            style={{ width: `${scale * 100}%` }}
            className="mx-auto block h-auto shadow-lg"
          />
        )}
        {kind === 'unsupported' && (
          <UnsupportedState type={blob.type} onDownload={handleDownload} />
        )}
      </div>
    </div>
  )
}
