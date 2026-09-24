import * as React from 'react'
import { Dialog as BaseDialog } from '@base-ui-components/react/dialog'
import { X } from 'lucide-react'
import { cn } from './cn'

export const Dialog = BaseDialog.Root
export const DialogTrigger = BaseDialog.Trigger
export const DialogClose = BaseDialog.Close

export const DialogContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseDialog.Popup> & { showClose?: boolean }
>(({ className, children, showClose = true, ...props }, ref) => (
  <BaseDialog.Portal>
    <BaseDialog.Backdrop className="fixed inset-0 z-50 bg-black/40 transition-opacity duration-200 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0" />
    <BaseDialog.Popup
      ref={ref}
      className={cn(
        'fixed top-1/2 left-1/2 z-50 flex w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col rounded-card border border-border bg-card text-card-foreground shadow-popover outline-none transition duration-200 data-[ending-style]:scale-95 data-[ending-style]:opacity-0 data-[starting-style]:scale-95 data-[starting-style]:opacity-0',
        // Centred on the viewport, so anything taller than it is clipped at both
        // ends with no way to reach the buttons. Capping the height and scrolling
        // inside keeps a long form — a company plus its ERP connection — usable
        // on a short window. `dvh` rather than `vh` so a mobile browser's
        // retracting toolbar does not hide the footer.
        // `overflow-hidden` so scrolling content passes under the rounded
        // corners rather than through them. Menus and pickers inside are
        // portalled to the body, so nothing that needs to escape is clipped.
        'max-h-[calc(100dvh-2rem)] overflow-hidden',
        className,
      )}
      {...props}
    >
      {/* The scroll lives here, not on the popup, so the close button below
          stays pinned to the corner instead of scrolling away with the form. */}
      <div className="grid gap-4 overflow-y-auto overscroll-contain p-6">
        {children}
      </div>
      {showClose && (
        <BaseDialog.Close className="absolute top-4 right-4 grid size-8 place-items-center rounded-full text-muted-foreground outline-none transition hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring">
          <X className="size-4" />
          <span className="sr-only">Close</span>
        </BaseDialog.Close>
      )}
    </BaseDialog.Popup>
  </BaseDialog.Portal>
))
DialogContent.displayName = 'DialogContent'

export function DialogHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex flex-col gap-1.5', className)} {...props} />
}

export function DialogFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'flex flex-col-reverse gap-2 sm:flex-row sm:justify-end',
        className,
      )}
      {...props}
    />
  )
}

export const DialogTitle = React.forwardRef<
  HTMLHeadingElement,
  React.ComponentProps<typeof BaseDialog.Title>
>(({ className, ...props }, ref) => (
  <BaseDialog.Title
    ref={ref}
    className={cn('font-display text-lg font-medium tracking-tight', className)}
    {...props}
  />
))
DialogTitle.displayName = 'DialogTitle'

export const DialogDescription = React.forwardRef<
  HTMLParagraphElement,
  React.ComponentProps<typeof BaseDialog.Description>
>(({ className, ...props }, ref) => (
  <BaseDialog.Description
    ref={ref}
    className={cn('text-sm text-muted-foreground', className)}
    {...props}
  />
))
DialogDescription.displayName = 'DialogDescription'
