import * as React from 'react'
import { useForm } from 'react-hook-form'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Badge,
  Button,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
} from '#/components/ui'
import { ApiError } from '#/lib/api-client'
import type { OrganizationRead } from '#/lib/types'
import { ReadOnlyNotice, SettingsCard, SubmitRow, useSettingsSubmit } from './form'
import { initials, validateImage } from './profile-panel'

export interface OrganizationValues {
  name: string
  slug: string
}

export interface OrganizationPanelProps {
  organization: OrganizationRead
  /** Renders the profile without controls when the caller may not edit it. */
  readOnly?: boolean
  onSave: (values: OrganizationValues) => Promise<unknown>
  logoUrl?: string
  onUploadLogo?: (file: File) => Promise<unknown>
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString()
}

export function OrganizationPanel({
  organization,
  readOnly = false,
  onSave,
  logoUrl,
  onUploadLogo,
}: OrganizationPanelProps) {
  const form = useForm<OrganizationValues>({
    defaultValues: { name: organization.name, slug: organization.slug ?? '' },
  })
  const submit = useSettingsSubmit()
  const fileInput = React.useRef<HTMLInputElement>(null)
  const [logoError, setLogoError] = React.useState<string | null>(null)
  const [logoBusy, setLogoBusy] = React.useState(false)

  const { name, slug } = organization
  const { reset, formState } = form
  React.useEffect(() => {
    if (!formState.isDirty) reset({ name, slug: slug ?? '' })
  }, [name, slug, reset, formState.isDirty])

  async function handleLogo(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !onUploadLogo) return
    const problem = validateImage(file)
    if (problem) {
      setLogoError(problem)
      return
    }
    setLogoError(null)
    setLogoBusy(true)
    try {
      await onUploadLogo(file)
    } catch (error) {
      setLogoError(error instanceof Error ? error.message : 'Couldn’t upload that logo.')
    } finally {
      setLogoBusy(false)
    }
  }

  const details = (
    <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
      <div className="flex items-center gap-2">
        <dt className="text-muted-foreground">Status</dt>
        <dd>
          <Badge variant={organization.status === 'suspended' ? 'destructive' : 'success'}>
            {organization.status}
          </Badge>
        </dd>
      </div>
      <div className="flex items-center gap-2">
        <dt className="text-muted-foreground">Created</dt>
        <dd>{formatDate(organization.created_at)}</dd>
      </div>
    </dl>
  )

  if (readOnly) {
    return (
      <SettingsCard title="Organization" description="Your workspace’s profile.">
        <div className="flex flex-col gap-4">
          <dl className="flex flex-col gap-3 text-sm">
            <div className="flex flex-col gap-1">
              <dt className="font-medium">Name</dt>
              <dd className="text-muted-foreground">{organization.name}</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="font-medium">Slug</dt>
              <dd className="text-muted-foreground">{organization.slug ?? '—'}</dd>
            </div>
          </dl>
          {details}
          <ReadOnlyNotice>
            Only an organization admin can change these details.
          </ReadOnlyNotice>
        </div>
      </SettingsCard>
    )
  }

  return (
    <SettingsCard title="Organization" description="Your workspace’s profile.">
      <div className="flex flex-col gap-6">
        {onUploadLogo ? (
          <div className="flex items-center gap-4">
            <Avatar className="size-16 rounded-xl">
              {logoUrl ? <AvatarImage src={logoUrl} alt={organization.name} /> : null}
              <AvatarFallback>{initials(organization.name)}</AvatarFallback>
            </Avatar>
            <div className="flex flex-col gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={logoBusy}
                onClick={() => fileInput.current?.click()}
              >
                {logoBusy ? 'Working…' : 'Change logo'}
              </Button>
              <input
                ref={fileInput}
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                className="hidden"
                aria-label="Organization logo"
                onChange={handleLogo}
              />
              {logoError ? <p className="text-sm text-destructive">{logoError}</p> : null}
            </div>
          </div>
        ) : null}

        <Form {...form}>
          <form
            className="flex max-w-md flex-col gap-4"
            onSubmit={submit({
              form,
              run: onSave,
              success: 'Organization updated',
              // A duplicate slug comes back as a 409 that names no field.
              fieldFor: (error) =>
                error instanceof ApiError && error.status === 409 ? 'slug' : undefined,
            })}
          >
            <FormField
              control={form.control}
              name="name"
              rules={{ required: 'Enter a name.' }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="slug"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Slug</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormDescription>Must be unique across all organizations.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <SubmitRow form={form} />
          </form>
        </Form>

        {details}
      </div>
    </SettingsCard>
  )
}
