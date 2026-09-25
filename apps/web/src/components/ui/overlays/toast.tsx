import * as React from 'react'
import { Toast } from '@base-ui-components/react/toast'
import { X } from 'lucide-react'
import { cn } from '../cn'

/** Access the toast manager: `const toast = useToast(); toast.add({ title })`. */
export const useToast = Toast.useToastManager

function ToastList() {
  const { toasts } = Toast.useToastManager()
  return toasts.map((toast) => (
    <Toast.Root
      key={toast.id}
      toast={toast}
      className={cn(
        'absolute right-0 bottom-0 left-auto z-[calc(1000-var(--toast-index))] w-80 rounded-lg border border-border bg-popover p-4 text-popover-foreground shadow-popover transition-all duration-300',
        '[transform:translateY(calc(var(--toast-index)*-14px))_scale(calc(1-var(--toast-index)*0.05)))] data-[expanded]:[transform:translateY(var(--toast-offset-y))]',
        'data-[ending-style]:opacity-0 data-[starting-style]:[transform:translateY(150%)]',
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <Toast.Title className="text-sm font-medium" />
          <Toast.Description className="mt-0.5 text-sm text-muted-foreground" />
        </div>
        <Toast.Close
          aria-label="Close"
          className="grid size-6 shrink-0 place-items-center rounded-full text-muted-foreground transition hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="size-3.5" />
        </Toast.Close>
      </div>
    </Toast.Root>
  ))
}

/** Wrap the app once to enable toasts anywhere via `useToast()`. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  return (
    <Toast.Provider>
      {children}
      <Toast.Portal>
        <Toast.Viewport className="fixed right-4 bottom-4 z-50 mx-auto flex w-80 sm:right-8 sm:bottom-8">
          <ToastList />
        </Toast.Viewport>
      </Toast.Portal>
    </Toast.Provider>
  )
}
