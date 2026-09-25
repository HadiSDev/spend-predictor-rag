import * as React from 'react'
import { cva } from 'class-variance-authority'
import type { VariantProps } from 'class-variance-authority'
import { cn } from '../cn'

export const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap [&_svg]:size-3',
  {
    variants: {
      variant: {
        default: 'bg-muted text-foreground',
        primary: 'bg-primary text-primary-foreground',
        outline: 'border border-border text-foreground',
        success: 'bg-success/12 text-success',
        warning: 'bg-warning/16 text-warning',
        destructive: 'bg-destructive/12 text-destructive',
        info: 'bg-info/12 text-info',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export interface BadgeProps
  extends
    React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}
