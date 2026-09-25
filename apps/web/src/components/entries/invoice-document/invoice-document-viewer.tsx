import * as React from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

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

/** A page slot that renders its page once scrolled into view. */
function PageSlot({ index, scale, registerRef }: PageSlotProps) {
  const [visible, setVisible] = React.useState(false)
  const elementRef = React.useRef<HTMLDivElement | null>(null)

  React.useEffect(() => {
    if (visible) {
      return
    }
    const el = elementRef.current
    if (!el) {
      return
    }
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true)
        }
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

/** Browser-only continuous PDF viewer for an invoice document. */
export default function InvoiceDocumentViewer({
  url,
  scale,
  pageNumber,
  onDocumentLoad,
  onDocumentError,
}: InvoiceDocumentViewerProps) {
  const [numPages, setNumPages] = React.useState(0)
  const pageRefs = React.useRef(new Map<number, HTMLDivElement>())

  const registerRef = React.useCallback(
    (index: number, el: HTMLDivElement | null) => {
      if (el) {
        pageRefs.current.set(index, el)
      } else {
        pageRefs.current.delete(index)
      }
    },
    [],
  )

  React.useEffect(() => {
    const el = pageRefs.current.get(pageNumber)
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({
        block: 'start',
        behavior: prefersReducedMotion() ? 'auto' : 'smooth',
      })
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
      onLoadError={(error) =>
        onDocumentError(
          error.message || 'This document could not be displayed.',
        )
      }
    >
      {Array.from({ length: numPages }, (_, i) => i + 1).map((index) => (
        <PageSlot
          key={index}
          index={index}
          scale={scale}
          registerRef={registerRef}
        />
      ))}
    </Document>
  )
}
