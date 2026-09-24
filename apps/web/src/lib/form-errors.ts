import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'
import { ApiError } from './api-client'

/**
 * The part of Clerk's API error shape we rely on. Duck-typed rather than
 * imported so this module stays usable wherever Clerk isn't mocked.
 */
interface ClerkFieldError {
  code?: string
  message?: string
  longMessage?: string
  meta?: { paramName?: string }
}

function clerkErrors(error: unknown): Array<ClerkFieldError> {
  if (typeof error !== 'object' || error === null || !('errors' in error)) return []
  const { errors } = error
  return Array.isArray(errors) ? errors : []
}

const GENERIC = 'Something went wrong. Please try again.'

/** Clerk's machine-readable reason (e.g. `form_password_incorrect`), if any. */
export function clerkErrorCode(error: unknown): string | undefined {
  const clerk = clerkErrors(error)
  return clerk.length > 0 ? clerk[0].code : undefined
}

/** The best message we can show the user for a failed write. */
export function serverErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  const clerk = clerkErrors(error)
  if (clerk.length > 0) return clerk[0].longMessage || clerk[0].message || GENERIC
  if (error instanceof Error) return error.message || GENERIC
  return GENERIC
}

/**
 * The field a server error is about, when it names one: Clerk reports it as
 * `meta.paramName`, and FastAPI's 422 detail is rendered as `field: message`
 * by `ApiError.detail`. Only fields the form actually owns are returned.
 */
function serverErrorField<T extends FieldValues>(
  error: unknown,
  fields: ReadonlyArray<Path<T>>,
): Path<T> | undefined {
  const isOwned = (name: string): name is Path<T> =>
    (fields as ReadonlyArray<string>).includes(name)

  const clerk = clerkErrors(error)
  const paramName = clerk.length > 0 ? clerk[0].meta?.paramName : undefined
  if (paramName && isOwned(paramName)) return paramName

  if (error instanceof ApiError) {
    const head = error.detail.split(':')[0].trim()
    if (head && isOwned(head)) return head
  }
  return undefined
}

export interface ApplyServerErrorOptions<T extends FieldValues> {
  /** Field names this form owns; an error naming one is attached to it. */
  fields?: ReadonlyArray<Path<T>>
  /** Explicit mapping for errors that don't name their field (e.g. a 409). */
  fieldFor?: (error: unknown) => Path<T> | undefined
}

/**
 * Put a failed write where the user can see it — on the offending field when
 * the server identifies one, otherwise on the form. Entered values are left
 * untouched so the user can correct and resubmit. Returns the message shown.
 */
export function applyServerError<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  { fields = [], fieldFor }: ApplyServerErrorOptions<T> = {},
): string {
  const message = serverErrorMessage(error)
  const field = fieldFor?.(error) ?? serverErrorField<T>(error, fields)
  if (field) {
    setError(field, { type: 'server', message })
  } else {
    setError('root', { type: 'server', message })
  }
  return message
}
