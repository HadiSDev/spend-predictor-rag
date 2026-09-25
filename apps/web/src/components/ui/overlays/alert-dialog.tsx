import * as React from 'react'
import { AlertDialog as BaseAlertDialog } from '@base-ui-components/react/alert-dialog'
import { cn } from '../cn'

export const AlertDialog = BaseAlertDialog.Root
export const AlertDialogTrigger = BaseAlertDialog.Trigger
export const AlertDialogClose = BaseAlertDialog.Close

export const AlertDialogContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseAlertDialog.Popup>
>(({ className, children, ...props }, ref) => (
  <BaseAlertDialog.Portal>
    <BaseAlertDialog.Backdrop className="fixed inset-0 z-50 bg-black/40 transition-opacity duration-200 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0" />
    <BaseAlertDialog.Popup
      ref={ref}
      className={cn(
        'fixed top-1/2 left-1/2 z-50 grid w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 gap-4 overflow-y-auto overscroll-contain rounded-card border border-border bg-card p-6 text-card-foreground shadow-popover outline-none transition duration-200 data-[ending-style]:scale-95 data-[ending-style]:opacity-0 data-[starting-style]:scale-95 data-[starting-style]:opacity-0',
        'max-h-[calc(100dvh-2rem)]',
        className,
      )}
      {...props}
    >
      {children}
    </BaseAlertDialog.Popup>
  </BaseAlertDialog.Portal>
))
AlertDialogContent.displayName = 'AlertDialogContent'

export function AlertDialogHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex flex-col gap-1.5', className)} {...props} />
}

export function AlertDialogFooter({
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

export const AlertDialogTitle = React.forwardRef<
  HTMLHeadingElement,
  React.ComponentProps<typeof BaseAlertDialog.Title>
>(({ className, ...props }, ref) => (
  <BaseAlertDialog.Title
    ref={ref}
    className={cn('font-display text-lg font-medium tracking-tight', className)}
    {...props}
  />
))
AlertDialogTitle.displayName = 'AlertDialogTitle'

export const AlertDialogDescription = React.forwardRef<
  HTMLParagraphElement,
  React.ComponentProps<typeof BaseAlertDialog.Description>
>(({ className, ...props }, ref) => (
  <BaseAlertDialog.Description
    ref={ref}
    className={cn('text-sm text-muted-foreground', className)}
    {...props}
  />
))
AlertDialogDescription.displayName = 'AlertDialogDescription'
