import * as React from 'react'
import { Calendar as CalendarIcon } from 'lucide-react'
import { cn } from '../cn'
import { Calendar } from './calendar'
import { fieldTriggerClassName } from './input'
import { Popover, PopoverContent, PopoverTrigger } from '../overlays/popover'

export interface DatePickerProps {
  value?: Date
  onChange?: (date: Date | undefined) => void
  placeholder?: string
  disabled?: boolean
  /** Month shown when first opened with no value. */
  defaultMonth?: Date
  className?: string
  /** Accessible name for the trigger. */
  'aria-label'?: string
}

const formatter = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' })

/** A date picker: a field-shaped trigger and a calendar in a popover. */
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
