import * as React from 'react'
import { Field as BaseField } from '@base-ui-components/react/field'
import { cn } from '../cn'
import { inputClassName } from './input'

/** Base UI Field.Root — wires label, control, error and description together. */
export const Field = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof BaseField.Root>
>(({ className, ...props }, ref) => (
  <BaseField.Root
    ref={ref}
    className={cn('flex flex-col gap-1.5', className)}
    {...props}
  />
))
Field.displayName = 'Field'

export const FieldLabel = React.forwardRef<
  HTMLLabelElement,
  React.ComponentProps<typeof BaseField.Label>
>(({ className, ...props }, ref) => (
  <BaseField.Label
    ref={ref}
    className={cn('text-sm font-medium text-foreground', className)}
    {...props}
  />
))
FieldLabel.displayName = 'FieldLabel'

/** A styled text control connected to the surrounding Field. */
export const FieldControl = React.forwardRef<
  HTMLInputElement,
  React.ComponentProps<typeof BaseField.Control>
>(({ className, ...props }, ref) => (
  <BaseField.Control
    ref={ref}
    className={cn(inputClassName, className)}
    {...props}
  />
))
FieldControl.displayName = 'FieldControl'

export const FieldDescription = React.forwardRef<
  HTMLParagraphElement,
  React.ComponentProps<typeof BaseField.Description>
>(({ className, ...props }, ref) => (
  <BaseField.Description
    ref={ref}
    className={cn('text-sm text-muted-foreground', className)}
    {...props}
  />
))
FieldDescription.displayName = 'FieldDescription'

export const FieldError = React.forwardRef<
  HTMLParagraphElement,
  React.ComponentProps<typeof BaseField.Error>
>(({ className, ...props }, ref) => (
  <BaseField.Error
    ref={ref}
    className={cn('text-sm text-destructive', className)}
    {...props}
  />
))
FieldError.displayName = 'FieldError'
