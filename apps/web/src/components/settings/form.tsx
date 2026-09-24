import * as React from 'react'
import { useFormState } from 'react-hook-form'
import type { FieldValues, Path, UseFormReturn } from 'react-hook-form'
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  useToast,
} from '#/components/ui'
import { applyServerError } from '#/lib/form-errors'

/** The card every settings panel sits in — title, optional description, body. */
export function SettingsCard({
  title,
  description,
  action,
  children,
  className,
}: {
  title: string
  description?: React.ReactNode
  /** Optional control rendered opposite the title (e.g. "Add company"). */
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <CardTitle>{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </div>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

/** A read-only notice explaining why a panel offers no controls. */
export function ReadOnlyNotice({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">{children}</p>
  )
}

/**
 * The submit contract shared by every settings form: submittable only when
 * dirty and valid, disabled and labelled "Saving…" while in flight, with any
 * form-level server error shown beside it.
 */
export function SubmitRow<T extends FieldValues>({
  form,
  label = 'Save changes',
  children,
}: {
  form: UseFormReturn<T>
  label?: string
  /** Extra controls (e.g. a cancel button) rendered after the submit button. */
  children?: React.ReactNode
}) {
  // Subscribe here so this row re-renders as the form's state changes.
  const { isDirty, isSubmitting, errors } = useFormState({ control: form.control })
  const rootError = errors.root?.message

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button type="submit" disabled={!isDirty || isSubmitting}>
        {isSubmitting ? 'Saving…' : label}
      </Button>
      {children}
      {rootError ? <p className="text-sm text-destructive">{String(rootError)}</p> : null}
    </div>
  )
}

/**
 * Thrown by `run` when it has already reported the write's outcome itself —
 * e.g. by opening its own confirmation dialog instead of completing the
 * write — so neither the generic success toast nor the generic failure one
 * applies to it. `run` remains responsible for showing the user whatever it
 * is they still need to see; this only stops the shared wrapper from also
 * claiming success (or a plain failure) on top of that.
 */
export class SubmitHandled extends Error {}

export interface SettingsSubmitOptions<T extends FieldValues> {
  form: UseFormReturn<T>
  /** Performs the write. Anything it throws is surfaced on the form, unless
   *  it is a `SubmitHandled` — see that class. */
  run: (values: T) => Promise<unknown>
  /** Toast title shown once the write succeeds. */
  success: string
  /** Map an error that doesn't name its field onto one (e.g. a 409 → `slug`). */
  fieldFor?: (error: unknown) => Path<T> | undefined
  /** Values to reset the form to on success. Defaults to what was submitted. */
  resetTo?: (values: T, result: unknown) => T
}

/**
 * Builds an `onSubmit` handler implementing the shared contract: success
 * toasts, the form reset to its saved values (so it is no longer dirty), and
 * failures mapped onto the offending field with the user's input preserved.
 */
export function useSettingsSubmit() {
  const toast = useToast()

  return React.useCallback(
    <T extends FieldValues>({
      form,
      run,
      success,
      fieldFor,
      resetTo,
    }: SettingsSubmitOptions<T>) =>
      form.handleSubmit(async (values) => {
        try {
          const result = await run(values)
          toast.add({ title: success })
          form.reset(resetTo ? resetTo(values, result) : values)
        } catch (error) {
          if (error instanceof SubmitHandled) return
          const message = applyServerError(error, form.setError, {
            fields: Object.keys(values) as Array<Path<T>>,
            fieldFor,
          })
          toast.add({ title: 'Couldn’t save your changes', description: message })
        }
      }),
    [toast],
  )
}
