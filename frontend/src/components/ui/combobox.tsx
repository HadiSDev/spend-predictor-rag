import * as React from 'react'
import { Combobox as BaseCombobox } from '@base-ui-components/react/combobox'
import { Separator as BaseSeparator } from '@base-ui-components/react/separator'
import { Check, ChevronDown, Loader2, X } from 'lucide-react'
import { cn } from './cn'
import { fieldTriggerClassName, inputClassName } from './input'

/**
 * Searchable select. A thin, token-styled wrapper over Base UI's headless
 * combobox — generic over the item type, so items can be strings or objects
 * (`itemToStringLabel` / `isItemEqualToValue` on the root handle the latter).
 *
 * Filtering is Base UI's built-in contains matching on the item label; pass
 * `filter` to change it or `filteredItems` to own filtering entirely.
 *
 *     <Combobox items={vendors} itemToStringLabel={(v) => v.name} onValueChange={pick}>
 *       <ComboboxInput placeholder="Search vendors" />
 *       <ComboboxContent>
 *         <ComboboxEmpty>No vendors found.</ComboboxEmpty>
 *         <ComboboxList>
 *           {(v: Vendor) => <ComboboxItem key={v.id} value={v}>{v.name}</ComboboxItem>}
 *         </ComboboxList>
 *       </ComboboxContent>
 *     </Combobox>
 */
export const Combobox = BaseCombobox.Root

/** Chevron slot for a trigger or an input-anchored affordance. */
export const ComboboxIcon = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseCombobox.Icon>
>(({ className, children, ...props }, ref) => (
  <BaseCombobox.Icon ref={ref} className={cn('text-muted-foreground', className)} {...props}>
    {children ?? <ChevronDown className="size-4" />}
  </BaseCombobox.Icon>
))
ComboboxIcon.displayName = 'ComboboxIcon'

export interface ComboboxInputProps extends React.ComponentProps<typeof BaseCombobox.Input> {
  /**
   * Rendered inside the field on the left — a flag, a status icon. Decorative:
   * pointer events pass through to the input beneath, so clicking it still
   * opens the list.
   */
  startAdornment?: React.ReactNode
  /**
   * Suppresses the chevron. For the one shape that does not want it: a search
   * input that lives *inside* an already-open popup, where there is nothing
   * left to open and the chevron would be a lie.
   */
  hideIcon?: boolean
}

/**
 * Text input that filters the list. Carries the `combobox` role.
 *
 * Wrapped rather than bare, because a text box that is really a select has to
 * say so: without the chevron it is indistinguishable from an `Input`, and a
 * user has no reason to click it expecting a list. `className` sizes the field
 * as a whole — `w-52` belongs here, not on the inner element.
 */
export const ComboboxInput = React.forwardRef<HTMLInputElement, ComboboxInputProps>(
  ({ className, startAdornment, hideIcon = false, ...props }, ref) => (
    <span className={cn('relative block', className)}>
      {startAdornment ? (
        <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2">
          {startAdornment}
        </span>
      ) : null}
      <BaseCombobox.Input
        ref={ref}
        className={cn(inputClassName, 'pr-9', startAdornment && 'pl-10')}
        {...props}
      />
      {hideIcon ? null : (
        // Decorative and click-through: Base UI opens the popup from the input
        // itself, so a nested button would only add a tab stop that does the
        // same thing.
        <ComboboxIcon className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2" />
      )}
    </span>
  ),
)
ComboboxInput.displayName = 'ComboboxInput'

/**
 * Button that opens the popup — for select-like comboboxes where the input
 * lives inside the popup. Pass `render` to restyle it completely.
 */
export const ComboboxTrigger = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<typeof BaseCombobox.Trigger>
>(({ className, children, ...props }, ref) => (
  <BaseCombobox.Trigger
    ref={ref}
    className={cn(fieldTriggerClassName, className)}
    {...props}
  >
    {children}
  </BaseCombobox.Trigger>
))
ComboboxTrigger.displayName = 'ComboboxTrigger'

/** Renders the selected value; accepts a function child for custom display. */
export const ComboboxValue = BaseCombobox.Value

/** Clears the selection. Only rendered when there is something to clear. */
export const ComboboxClear = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<typeof BaseCombobox.Clear>
>(({ className, children, ...props }, ref) => (
  <BaseCombobox.Clear
    ref={ref}
    className={cn(
      'grid size-6 place-items-center rounded-md text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring',
      className,
    )}
    {...props}
  >
    {children ?? <X className="size-4" />}
  </BaseCombobox.Clear>
))
ComboboxClear.displayName = 'ComboboxClear'

export interface ComboboxContentProps extends React.ComponentProps<typeof BaseCombobox.Popup> {
  /** Distance between the anchor and the popup. */
  sideOffset?: number
  /**
   * Items are still loading. Shows a loading indication *instead of* the
   * children, so a caller never flashes an empty or "no matches" list while a
   * fetch is in flight.
   */
  loading?: boolean
  /** Label for the loading indication. */
  loadingLabel?: string
}

/** Portal + Positioner + Popup, matching `SelectContent`. */
export const ComboboxContent = React.forwardRef<HTMLDivElement, ComboboxContentProps>(
  ({ className, children, sideOffset = 6, loading, loadingLabel = 'Loading…', ...props }, ref) => (
    <BaseCombobox.Portal>
      <BaseCombobox.Positioner className="z-50 outline-none" sideOffset={sideOffset}>
        <BaseCombobox.Popup
          ref={ref}
          className={cn(
            'min-w-[var(--anchor-width)] rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover',
            className,
          )}
          {...props}
        >
          {loading ? (
            <div
              role="status"
              className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground"
            >
              <Loader2 className="size-4 animate-spin" />
              {loadingLabel}
            </div>
          ) : (
            children
          )}
        </BaseCombobox.Popup>
      </BaseCombobox.Positioner>
    </BaseCombobox.Portal>
  ),
)
ComboboxContent.displayName = 'ComboboxContent'

/**
 * The scrollable option list. Accepts a function child that Base UI calls per
 * item when the root was given `items`.
 */
export const ComboboxList = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseCombobox.List>
>(({ className, ...props }, ref) => (
  <BaseCombobox.List
    ref={ref}
    className={cn('max-h-72 overflow-y-auto overscroll-contain', className)}
    {...props}
  />
))
ComboboxList.displayName = 'ComboboxList'

export const ComboboxItem = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseCombobox.Item>
>(({ className, children, ...props }, ref) => (
  <BaseCombobox.Item
    ref={ref}
    className={cn(
      'relative flex cursor-default items-center rounded-md py-1.5 pr-8 pl-3 text-sm outline-none select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[highlighted]:bg-muted',
      className,
    )}
    {...props}
  >
    {children}
    <BaseCombobox.ItemIndicator className="absolute right-2 flex">
      <Check className="size-4" />
    </BaseCombobox.ItemIndicator>
  </BaseCombobox.Item>
))
ComboboxItem.displayName = 'ComboboxItem'

/** Shown in place of the list when the query matches nothing. */
export const ComboboxEmpty = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseCombobox.Empty>
>(({ className, children, ...props }, ref) => (
  <BaseCombobox.Empty
    ref={ref}
    className={cn('px-3 py-2 text-sm text-muted-foreground', className)}
    {...props}
  >
    {children ?? 'No results found.'}
  </BaseCombobox.Empty>
))
ComboboxEmpty.displayName = 'ComboboxEmpty'

/** Live region announcing result counts to assistive technology. */
export const ComboboxStatus = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseCombobox.Status>
>(({ className, ...props }, ref) => (
  <BaseCombobox.Status
    ref={ref}
    className={cn('px-3 py-2 text-sm text-muted-foreground', className)}
    {...props}
  />
))
ComboboxStatus.displayName = 'ComboboxStatus'

export const ComboboxGroup = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseCombobox.Group>
>(({ className, ...props }, ref) => (
  <BaseCombobox.Group ref={ref} className={cn('py-1 first:pt-0 last:pb-0', className)} {...props} />
))
ComboboxGroup.displayName = 'ComboboxGroup'

export const ComboboxGroupLabel = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseCombobox.GroupLabel>
>(({ className, ...props }, ref) => (
  <BaseCombobox.GroupLabel
    ref={ref}
    className={cn('px-3 py-1.5 text-xs font-medium text-muted-foreground', className)}
    {...props}
  />
))
ComboboxGroupLabel.displayName = 'ComboboxGroupLabel'

export const ComboboxSeparator = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseSeparator>
>(({ className, ...props }, ref) => (
  <BaseSeparator ref={ref} className={cn('-mx-1 my-1 h-px bg-border', className)} {...props} />
))
ComboboxSeparator.displayName = 'ComboboxSeparator'
