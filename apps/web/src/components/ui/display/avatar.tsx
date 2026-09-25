import * as React from 'react'
import { Avatar as BaseAvatar } from '@base-ui-components/react/avatar'
import { cn } from '../cn'

export const Avatar = React.forwardRef<
  HTMLSpanElement,
  React.ComponentProps<typeof BaseAvatar.Root>
>(({ className, ...props }, ref) => (
  <BaseAvatar.Root
    ref={ref}
    className={cn(
      'inline-flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted align-middle text-sm font-medium text-muted-foreground select-none',
      className,
    )}
    {...props}
  />
))
Avatar.displayName = 'Avatar'

export const AvatarImage = React.forwardRef<
  HTMLImageElement,
  React.ComponentProps<typeof BaseAvatar.Image>
>(({ className, ...props }, ref) => (
  <BaseAvatar.Image
    ref={ref}
    className={cn('size-full object-cover', className)}
    {...props}
  />
))
AvatarImage.displayName = 'AvatarImage'

export const AvatarFallback = React.forwardRef<
  HTMLSpanElement,
  React.ComponentProps<typeof BaseAvatar.Fallback>
>(({ className, ...props }, ref) => (
  <BaseAvatar.Fallback
    ref={ref}
    className={cn('flex size-full items-center justify-center', className)}
    {...props}
  />
))
AvatarFallback.displayName = 'AvatarFallback'
