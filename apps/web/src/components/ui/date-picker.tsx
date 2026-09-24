import * as React from 'react'
import { Calendar as CalendarIcon } from 'lucide-react'
import { cn } from './cn'
import { Calendar } from './calendar'
import { fieldTriggerClassName } from './input'
import { Popover, PopoverContent, PopoverTrigger } from './popover'

export interface DatePickerProps {
  value?: Date
  onChange?: (date: Date | undefined) => void
  placeholder?: string
  disabled?: boolean
  /** Month shown when first opened with no value. */
  defaultMonth?: Date
  className?: string
  /**
   * What date this picks.
   *
   * The trigger's only content is the formatted date, so without this its
   * accessible name is a date and nothing else — the From and To pickers in the
   * filter bar were announced identically, and a picker beside a label had no
   * programmatic tie to it (Base UI's `Field` wires its own `Field.Control`,
   * not an arbitrary trigger).
   */
  'aria-label'?: string
}

const formatter = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' })

/**
 * A date picker: a field-shaped trigger + a calendar in a popover.
 *
 * The trigger is a button but must not *look* like one. It holds a value and
 * sits in filter rows beside selects and comboboxes, so it takes the same field
 * shape they do (`fieldTriggerClassName`) rather than `Button`, whose pill
 * radius and transparent fill made it read as an action among controls.
 */
export function DatePicker({
  value,
  onChange,
  placeholder = 'Pick a date',
  disabled,
  defaultMonth,
  className,
  'aria-label': ariaLabel,
}: DatePickerProps) {
  const [open, setOpen] = React.useState(false)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <button
            type="button"
            disabled={disabled}
            aria-label={ariaLabel}
            className={cn(fieldTriggerClassName, className)}
          >
            {/* Muted only when it is a placeholder, so a set date carries the
                same ink as a chosen select value beside it. */}
            <span className={cn('truncate', !value && 'text-muted-foreground')}>
              {value ? formatter.format(value) : placeholder}
            </span>
            <CalendarIcon className="size-4 shrink-0 text-muted-foreground" />
          </button>
        }
      />
      <PopoverContent align="start" className="w-auto p-2">
        <Calendar
          mode="single"
          selected={value}
          defaultMonth={defaultMonth ?? value}
          onSelect={(date) => {
            onChange?.(date)
            setOpen(false)
          }}
          autoFocus
        />
      </PopoverContent>
    </Popover>
  )
}
