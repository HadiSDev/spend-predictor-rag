// Browser-only: pdf.js touches `DOMMatrix`, `Worker` and `canvas`, none of
// which exist server-side, so this module is never imported statically —
// `invoice-document.tsx` reaches it only through `React.lazy(() =>
// import('./invoice-document-viewer'))`, itself gated behind `ClientOnly` so
// the dynamic import is never even attempted during SSR (see
// invoice-document.ssr.test.tsx, which proves both halves of that claim: the
// bare package really does crash under Node, and the guarded path really
// doesn't reach it).
import * as React from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

// Per react-pdf's docs, this must be set in the same module that renders
// `<Document>`/`<Page>` — setting it elsewhere risks another import order
// resetting it to the (broken) default before this file's first render.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

interface PageSlotProps {
  index: number
  scale: number
  registerRef: (index: number, el: HTMLDivElement | null) => void
}

/**
 * One page's slot. The `<Page>` itself — pdf.js rasterizing a canvas — only
 * mounts once the slot has scrolled into view at least once; react-pdf would
 * otherwise rasterize every page in the document up front, which stalls the
 * main thread on a long invoice. A page that has been shown stays mounted
 * rather than unmounting again on scroll-away: re-rasterizing on every pass
 * would cost more than the memory it saves.
 */
function PageSlot({ index, scale, registerRef }: PageSlotProps) {
  const [visible, setVisible] = React.useState(false)
  const elementRef = React.useRef<HTMLDivElement | null>(null)

  React.useEffect(() => {
    if (visible) return
    const el = elementRef.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      // No observer support: fail open rather than never rendering the page.
      setVisible(true)
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setVisible(true)
      },
      { rootMargin: '200px 0px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [visible])

  return (
    <div
      ref={(el) => {
        elementRef.current = el
        registerRef(index, el)
      }}
      data-testid={`invoice-page-slot-${index}`}
      className="mx-auto mb-4 w-fit [content-visibility:auto]"
    >
      {visible ? (
        <Page
          pageNumber={index}
          scale={scale}
          className="shadow-lg"
          renderAnnotationLayer
          renderTextLayer
        />
      ) : (
        // A same-sized placeholder so the scrollbar/observer geometry stays
        // stable once the real page swaps in.
        <div className="h-200 w-150 rounded-sm bg-card" aria-hidden="true" />
      )}
    </div>
  )
}

export interface InvoiceDocumentViewerProps {
  /** Object URL for the fetched blob. */
  url: string
  scale: number
  /** The page to scroll to when this changes. */
  pageNumber: number
  onDocumentLoad: (numPages: number) => void
  onDocumentError: (message: string) => void
}

/**
 * Renders every page of the document, continuously, with only the pages that
 * have scrolled into view actually rasterized (see `PageSlot`). Mounted by
 * `invoice-document.tsx` through `React.lazy` + `ClientOnly`.
 */
export default function InvoiceDocumentViewer({
  url,
  scale,
  pageNumber,
  onDocumentLoad,
  onDocumentError,
}: InvoiceDocumentViewerProps) {
  const [numPages, setNumPages] = React.useState(0)
  const pageRefs = React.useRef(new Map<number, HTMLDivElement>())

  const registerRef = React.useCallback((index: number, el: HTMLDivElement | null) => {
    if (el) pageRefs.current.set(index, el)
    else pageRefs.current.delete(index)
  }, [])

  React.useEffect(() => {
    const el = pageRefs.current.get(pageNumber)
    // Defensive: some DOM implementations (older jsdom, certain embedded
    // webviews) don't implement scrollIntoView at all.
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'start', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
    }
  }, [pageNumber])

  return (
    <Document
      file={url}
      loading={null}
      error={null}
      noData={null}
      onLoadSuccess={(pdf) => {
        setNumPages(pdf.numPages)
        onDocumentLoad(pdf.numPages)
      }}
      onLoadError={(error) => onDocumentError(error.message || 'This document could not be displayed.')}
    >
      {Array.from({ length: numPages }, (_, i) => i + 1).map((index) => (
        <PageSlot key={index} index={index} scale={scale} registerRef={registerRef} />
      ))}
    </Document>
  )
}
