import * as React from 'react'
import { useForm } from 'react-hook-form'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Button,
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
} from '#/components/ui'
import {
  SettingsCard,
  SubmitRow,
  useSettingsSubmit,
} from '#/components/settings/form'

export interface ProfileValues {
  firstName: string
  lastName: string
}

/** Avatar image types Clerk accepts. */
const ACCEPTED_IMAGE_TYPES = [
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
]
const MAX_IMAGE_BYTES = 5 * 1024 * 1024

/** Reject an obviously bad file before spending an upload on it. */
export function validateImage(file: File): string | null {
  if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
    return 'Choose a PNG, JPEG, GIF, or WebP image.'
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return 'That image is larger than 5 MB. Choose a smaller one.'
  }
  return null
}

export function initials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) {
    return '?'
  }
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase()
  }
  return (parts[0][0] + parts[1][0]).toUpperCase()
}

export interface ProfilePanelProps {
  defaultValues: ProfileValues
  /** Name shown beside the avatar, and the source of its fallback initials. */
  displayName: string
  email: string
  imageUrl?: string
  onSave: (values: ProfileValues) => Promise<unknown>
  onUploadImage: (file: File) => Promise<unknown>
  onRemoveImage: () => Promise<unknown>
}

/** Personal identity: name plus avatar. */
export function ProfilePanel({
  defaultValues,
  displayName,
  email,
  imageUrl,
  onSave,
  onUploadImage,
  onRemoveImage,
}: ProfilePanelProps) {
  const form = useForm<ProfileValues>({ defaultValues })
  const submit = useSettingsSubmit()
  const fileInput = React.useRef<HTMLInputElement>(null)
  const [imageError, setImageError] = React.useState<string | null>(null)
  const [imageBusy, setImageBusy] = React.useState(false)

  const { firstName, lastName } = defaultValues
  const { reset, formState } = form
  React.useEffect(() => {
    if (!formState.isDirty) {
      reset({ firstName, lastName })
    }
  }, [firstName, lastName, reset, formState.isDirty])

  async function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) {
      return
    }
    const problem = validateImage(file)
    if (problem) {
      setImageError(problem)
      return
    }
    setImageError(null)
    setImageBusy(true)
    try {
      await onUploadImage(file)
    } catch (error) {
      setImageError(
        error instanceof Error ? error.message : 'Couldn’t upload that image.',
      )
    } finally {
      setImageBusy(false)
    }
  }

  async function handleRemoveImage() {
    setImageBusy(true)
    setImageError(null)
    try {
      await onRemoveImage()
    } catch (error) {
      setImageError(
        error instanceof Error ? error.message : 'Couldn’t remove your photo.',
      )
    } finally {
      setImageBusy(false)
    }
  }

  return (
    <SettingsCard
      title="Profile"
      description="How you appear across the workspace."
    >
      <div className="flex flex-col gap-6">
        <div className="flex items-center gap-4">
          <Avatar className="size-16">
            {imageUrl ? <AvatarImage src={imageUrl} alt={displayName} /> : null}
            <AvatarFallback>{initials(displayName)}</AvatarFallback>
          </Avatar>
          <div className="flex min-w-0 flex-col gap-2">
            <div className="truncate text-sm text-muted-foreground">
              {email}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={imageBusy}
                onClick={() => fileInput.current?.click()}
              >
                {imageBusy ? 'Working…' : 'Change photo'}
              </Button>
              {imageUrl ? (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={imageBusy}
                  onClick={handleRemoveImage}
                >
                  Remove
                </Button>
              ) : null}
            </div>
            <input
              ref={fileInput}
              type="file"
              accept={ACCEPTED_IMAGE_TYPES.join(',')}
              className="hidden"
              aria-label="Profile photo"
              onChange={handleFile}
            />
            {imageError ? (
              <p className="text-sm text-destructive">{imageError}</p>
            ) : null}
          </div>
        </div>

        <Form {...form}>
          <form
            className="flex flex-col gap-4"
            onSubmit={submit({ form, run: onSave, success: 'Profile updated' })}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="firstName"
                rules={{
                  maxLength: {
                    value: 60,
                    message: 'Keep it under 60 characters.',
                  },
                }}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>First name</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="lastName"
                rules={{
                  maxLength: {
                    value: 60,
                    message: 'Keep it under 60 characters.',
                  },
                }}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Last name</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <SubmitRow form={form} />
          </form>
        </Form>
      </div>
    </SettingsCard>
  )
}
