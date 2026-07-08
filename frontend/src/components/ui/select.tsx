import * as React from 'react'
import { Select as BaseSelect } from '@base-ui-components/react/select'
import { Check, ChevronDown } from 'lucide-react'
import { cn } from './cn'

export const Select = BaseSelect.Root
export const SelectGroup = BaseSelect.Group

export const SelectTrigger = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<typeof BaseSelect.Trigger>
>(({ className, children, ...props }, ref) => (
  <BaseSelect.Trigger
    ref={ref}
    className={cn(
      'flex h-10 w-full items-center justify-between gap-2 rounded-md border border-input bg-card px-3 text-sm text-foreground outline-none transition focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50',
      className,
    )}
    {...props}
  >
    {children}
    <BaseSelect.Icon className="text-muted-foreground">
      <ChevronDown className="size-4" />
    </BaseSelect.Icon>
  </BaseSelect.Trigger>
))
SelectTrigger.displayName = 'SelectTrigger'

export function SelectValue({
  placeholder,
  className,
}: {
  placeholder?: string
  className?: string
}) {
  return (
    <BaseSelect.Value className={className}>
      {(value: unknown) =>
        value === null || value === undefined || value === '' ? (
          <span className="text-muted-foreground">{placeholder}</span>
        ) : (
          (value as React.ReactNode)
        )
      }
    </BaseSelect.Value>
  )
}

export const SelectContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseSelect.Popup>
>(({ className, children, ...props }, ref) => (
  <BaseSelect.Portal>
    <BaseSelect.Positioner className="z-50 outline-none" sideOffset={6}>
      <BaseSelect.Popup
        ref={ref}
        className={cn(
          'max-h-72 min-w-[var(--anchor-width)] overflow-y-auto rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover',
          className,
        )}
        {...props}
      >
        {children}
      </BaseSelect.Popup>
    </BaseSelect.Positioner>
  </BaseSelect.Portal>
))
SelectContent.displayName = 'SelectContent'

export const SelectItem = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseSelect.Item>
>(({ className, children, ...props }, ref) => (
  <BaseSelect.Item
    ref={ref}
    className={cn(
      'relative flex cursor-default items-center rounded-md py-1.5 pr-8 pl-3 text-sm outline-none select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[highlighted]:bg-muted',
      className,
    )}
    {...props}
  >
    <BaseSelect.ItemText>{children}</BaseSelect.ItemText>
    <BaseSelect.ItemIndicator className="absolute right-2 flex">
      <Check className="size-4" />
    </BaseSelect.ItemIndicator>
  </BaseSelect.Item>
))
SelectItem.displayName = 'SelectItem'

export const SelectGroupLabel = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseSelect.GroupLabel>
>(({ className, ...props }, ref) => (
  <BaseSelect.GroupLabel
    ref={ref}
    className={cn('px-3 py-1.5 text-xs font-medium text-muted-foreground', className)}
    {...props}
  />
))
SelectGroupLabel.displayName = 'SelectGroupLabel'

export const SelectSeparator = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseSelect.Separator>
>(({ className, ...props }, ref) => (
  <BaseSelect.Separator ref={ref} className={cn('-mx-1 my-1 h-px bg-border', className)} {...props} />
))
SelectSeparator.displayName = 'SelectSeparator'
