import * as React from 'react'
import type { VariantProps } from 'class-variance-authority'
import { buttonVariants } from './button'
import { cn } from '../cn'

export interface IconButtonProps
  extends
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    Omit<VariantProps<typeof buttonVariants>, 'size'> {
  'aria-label': string
}

/** A square, icon-only button. `aria-label` is required for accessibility. */
export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className, variant = 'ghost', type = 'button', ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(buttonVariants({ variant, size: 'icon' }), className)}
      {...props}
    />
  ),
)
IconButton.displayName = 'IconButton'
