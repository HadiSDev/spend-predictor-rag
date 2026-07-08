import * as React from 'react'
import { Calendar as CalendarIcon } from 'lucide-react'
import { cn } from './cn'
import { Button } from './button'
import { Calendar } from './calendar'
import { Popover, PopoverContent, PopoverTrigger } from './popover'

export interface DatePickerProps {
  value?: Date
  onChange?: (date: Date | undefined) => void
  placeholder?: string
  disabled?: boolean
  /** Month shown when first opened with no value. */
  defaultMonth?: Date
  className?: string
}

const formatter = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' })

/** A date picker: a themed trigger button + a calendar in a popover. */
export function DatePicker({
  value,
  onChange,
  placeholder = 'Pick a date',
  disabled,
  defaultMonth,
  className,
}: DatePickerProps) {
  const [open, setOpen] = React.useState(false)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant="outline"
            disabled={disabled}
            className={cn('w-56 justify-between font-normal', !value && 'text-muted-foreground', className)}
          >
            {value ? formatter.format(value) : placeholder}
            <CalendarIcon className="size-4 opacity-70" />
          </Button>
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
