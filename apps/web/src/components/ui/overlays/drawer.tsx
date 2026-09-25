import * as React from 'react'
import { Dialog as BaseDialog } from '@base-ui-components/react/dialog'
import { X } from 'lucide-react'
import { cn } from '../cn'

/** A side-anchored panel built on the Base UI dialog primitive. */
export const Drawer = BaseDialog.Root
export const DrawerTrigger = BaseDialog.Trigger
export const DrawerClose = BaseDialog.Close

const sideClass = {
  right:
    'inset-y-0 right-0 border-l data-[ending-style]:translate-x-full data-[starting-style]:translate-x-full',
  left: 'inset-y-0 left-0 border-r data-[ending-style]:-translate-x-full data-[starting-style]:-translate-x-full',
} as const

const sizeClass = {
  default: 'max-w-md',
  wide: 'max-w-[1100px] w-[92vw]',
} as const

export interface DrawerContentProps extends React.ComponentProps<
  typeof BaseDialog.Popup
> {
  side?: keyof typeof sideClass
  size?: keyof typeof sizeClass
  showClose?: boolean
}

export const DrawerContent = React.forwardRef<
  HTMLDivElement,
  DrawerContentProps
>(
  (
    {
      className,
      children,
      side = 'right',
      size = 'default',
      showClose = true,
      ...props
    },
    ref,
  ) => (
    <BaseDialog.Portal>
      <BaseDialog.Backdrop className="fixed inset-0 z-50 bg-black/40 transition-opacity duration-200 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0" />
      <BaseDialog.Popup
        ref={ref}
        className={cn(
          'fixed z-50 flex w-[calc(100%-3rem)] flex-col gap-4 overflow-y-auto border-border bg-card p-6 text-card-foreground shadow-popover outline-none transition-transform duration-200',
          sideClass[side],
          sizeClass[size],
          className,
        )}
        {...props}
      >
        {children}
        {showClose && (
          <BaseDialog.Close className="absolute top-4 right-4 grid size-8 place-items-center rounded-full text-muted-foreground outline-none transition hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring">
            <X className="size-4" />
            <span className="sr-only">Close</span>
          </BaseDialog.Close>
        )}
      </BaseDialog.Popup>
    </BaseDialog.Portal>
  ),
)
DrawerContent.displayName = 'DrawerContent'

export function DrawerHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('flex flex-col gap-1.5 pr-10', className)} {...props} />
  )
}

export function DrawerFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'mt-auto flex flex-col-reverse gap-2 sm:flex-row sm:justify-end',
        className,
      )}
      {...props}
    />
  )
}

export const DrawerTitle = React.forwardRef<
  HTMLHeadingElement,
  React.ComponentProps<typeof BaseDialog.Title>
>(({ className, ...props }, ref) => (
  <BaseDialog.Title
    ref={ref}
    className={cn('font-display text-lg font-medium tracking-tight', className)}
    {...props}
  />
))
DrawerTitle.displayName = 'DrawerTitle'

export const DrawerDescription = React.forwardRef<
  HTMLParagraphElement,
  React.ComponentProps<typeof BaseDialog.Description>
>(({ className, ...props }, ref) => (
  <BaseDialog.Description
    ref={ref}
    className={cn('text-sm text-muted-foreground', className)}
    {...props}
  />
))
DrawerDescription.displayName = 'DrawerDescription'
