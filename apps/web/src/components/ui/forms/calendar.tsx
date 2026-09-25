import { DayPicker } from 'react-day-picker'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '../cn'

export type CalendarProps = React.ComponentProps<typeof DayPicker>

/** Themed react-day-picker calendar. */
export function Calendar({ className, ...props }: CalendarProps) {
  return (
    <DayPicker
      className={cn('p-1', className)}
      components={{
        Chevron: ({ orientation }) =>
          orientation === 'left' ? (
            <ChevronLeft className="size-4" />
          ) : (
            <ChevronRight className="size-4" />
          ),
      }}
      {...props}
    />
  )
}
