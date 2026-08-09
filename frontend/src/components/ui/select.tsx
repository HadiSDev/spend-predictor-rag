import * as React from 'react'
import { Select as BaseSelect } from '@base-ui-components/react/select'
import { Check, ChevronDown } from 'lucide-react'
import { cn } from './cn'
import { fieldTriggerClassName } from './input'

export const Select = BaseSelect.Root
export const SelectGroup = BaseSelect.Group

export const SelectTrigger = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<typeof BaseSelect.Trigger>
>(({ className, children, ...props }, ref) => (
  <BaseSelect.Trigger
    ref={ref}
    className={cn(fieldTriggerClassName, className)}
    {...props}
  >
    {children}
    {/* `shrink-0`: a long value truncates (see `SelectValue`) instead of
        squeezing the chevron until it disappears. */}
    <BaseSelect.Icon className="shrink-0 text-muted-foreground">
      <ChevronDown className="size-4" />
    </BaseSelect.Icon>
  </BaseSelect.Trigger>
))
SelectTrigger.displayName = 'SelectTrigger'

export function SelectValue({
  placeholder,
  className,
  items,
}: {
  placeholder?: string
  className?: string
  /**
   * Value → label pairs, for when the values aren't display text (e.g. Clerk
   * role keys like `org:member`). Base UI resolves labels from the root's own
   * `items` only when `Select.Value` has no children — and this component
   * always passes a function child to render the placeholder — so the mapping
   * has to happen here.
   */
  items?: ReadonlyArray<{ value: unknown; label: React.ReactNode }>
}) {
  return (
    // `min-w-0 truncate`: the trigger is a fixed width and the values are user
    // data — a company or supplier name has no bound — so a long one is cut off
    // here rather than pushing the chevron out of the control. The full label is
    // never lost: the popup wraps it (see `SelectItem`).
    <BaseSelect.Value className={cn('min-w-0 truncate', className)}>
      {(value: unknown) => {
        if (value === null || value === undefined || value === '') {
          return <span className="text-muted-foreground">{placeholder}</span>
        }
        const match = items?.find((item) => item.value === value)
        return (match ? match.label : value) as React.ReactNode
      }}
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
      // `whitespace-normal`: an option longer than the trigger wraps onto a
      // second line rather than being clipped. The popup is only as wide as the
      // control that anchors it, and every filter's options are user data —
      // company and supplier names — so there is no width at which clipping is
      // safe. `items-start` keeps the check mark aligned with the first line of
      // a wrapped label instead of floating at its vertical centre.
      'relative flex cursor-default items-start gap-2 rounded-md py-1.5 pr-8 pl-3 text-sm whitespace-normal outline-none select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[highlighted]:bg-muted',
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
