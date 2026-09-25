import type { useForm } from 'react-hook-form'
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  Switch,
} from '#/components/ui'
import type { ErpIntegrationRead, ErpTypeRead } from '#/lib/api/types'
import { defaultCredentials } from './company-values'
import type { CompanyFormValues } from './company-values'
import { ErpTypeGrid } from './erp-type-grid'

/** The ERP connection fields, in `create`, `edit` or `connect` mode. */
export function ErpConnectionFields({
  form,
  erpTypes,
  loading,
  mode,
  integration,
  otherCount,
}: {
  form: ReturnType<typeof useForm<CompanyFormValues>>
  erpTypes: Array<ErpTypeRead>
  loading: boolean
  mode: 'create' | 'edit' | 'connect'
  integration?: ErpIntegrationRead
  otherCount: number
}) {
  const selected = form.watch('erp_type')
  const replacing = form.watch('replaceCredentials')
  const switching =
    mode === 'edit' && !!selected && selected !== integration?.erp_type
  const active = erpTypes.find(
    (type) =>
      type.erp_type ===
      (mode === 'edit' && !switching ? integration?.erp_type : selected),
  )
  const credentialFields = !active
    ? []
    : mode === 'edit' && !switching && !replacing
      ? []
      : active.credential_fields
  const connectedNotOffered =
    mode === 'edit' &&
    !!integration &&
    !switching &&
    !erpTypes.some((type) => type.erp_type === integration.erp_type)

  return (
    <div className="flex flex-col gap-4 border-t border-border pt-4">
      <div>
        <h3 className="text-sm font-medium">ERP connection</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {mode === 'create'
            ? 'A company without one syncs nothing, so it is connected up front.'
            : mode === 'connect'
              ? 'This company is not connected to an ERP, so it syncs nothing. Connect one to start.'
              : 'Where this company’s ERP data is read from.'}
        </p>
        {otherCount > 0 ? (
          <p className="mt-1 text-sm text-muted-foreground">
            This company has {otherCount} other{' '}
            {otherCount === 1 ? 'integration' : 'integrations'}, managed outside
            this dialog.
          </p>
        ) : null}
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading ERP systems…</p>
      ) : mode !== 'edit' && erpTypes.length === 0 ? (
        <p className="text-sm text-destructive">
          No ERP systems are available to connect. Check the web API
          configuration.
        </p>
      ) : (
        <>
          {mode === 'edit' && integration ? (
            <>
              <FormField
                control={form.control}
                name="label"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Connection label (optional)</FormLabel>
                    <FormControl>
                      <Input placeholder="Main" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {switching ? null : (
                <div className="flex flex-col gap-2">
                  <label className="flex items-center gap-3 text-sm">
                    <Switch
                      checked={replacing}
                      onCheckedChange={(next: boolean) => {
                        form.setValue('replaceCredentials', next)
                        form.setValue(
                          'credentials',
                          next
                            ? defaultCredentials(
                                erpTypes.find(
                                  (t) => t.erp_type === integration.erp_type,
                                ),
                              )
                            : {},
                        )
                      }}
                      aria-label="Replace credentials"
                    />
                    Replace credentials
                  </label>
                  <p className="text-sm text-muted-foreground">
                    {integration.has_credentials
                      ? 'Credentials are set. They are never shown, so replacing them means entering every field again.'
                      : 'No credentials are stored; the connector falls back to its defaults.'}
                  </p>
                </div>
              )}
            </>
          ) : null}

          {connectedNotOffered ? (
            <p className="text-sm text-muted-foreground">
              Currently connected to{' '}
              <span className="font-medium text-foreground">
                {integration.erp_type}
              </span>
              , which is not in the list below.
            </p>
          ) : null}

          <FormField
            control={form.control}
            name="erp_type"
            rules={
              mode === 'create'
                ? { required: 'Choose an ERP system.' }
                : undefined
            }
            render={({ field }) => (
              <FormItem>
                <FormLabel>ERP system</FormLabel>
                <FormControl>
                  <ErpTypeGrid
                    erpTypes={erpTypes}
                    value={field.value}
                    onSelect={(next) => {
                      field.onChange(next)
                      form.setValue(
                        'credentials',
                        defaultCredentials(
                          erpTypes.find((t) => t.erp_type === next),
                        ),
                      )
                      form.setValue('replaceCredentials', false)
                    }}
                  />
                </FormControl>
                {mode === 'edit' ? (
                  <FormDescription>
                    Choosing a different system retires this connection and
                    starts a new one. Nothing already synced is deleted.
                  </FormDescription>
                ) : null}
                <FormMessage />
              </FormItem>
            )}
          />

          {mode === 'connect' && active ? (
            <FormField
              control={form.control}
              name="label"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Connection label (optional)</FormLabel>
                  <FormControl>
                    <Input placeholder="Main" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          ) : null}

          {credentialFields.map((credential) => (
            <FormField
              key={credential.name}
              control={form.control}
              name={`credentials.${credential.name}` as const}
              rules={
                credential.required
                  ? {
                      validate: (value: string) =>
                        value.trim().length > 0 ||
                        `Enter the ${credential.label.toLowerCase()}.`,
                    }
                  : undefined
              }
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {credential.label}
                    {credential.required ? '' : ' (optional)'}
                  </FormLabel>
                  <FormControl>
                    <Input
                      type={credential.secret ? 'password' : 'text'}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          ))}
        </>
      )}
    </div>
  )
}
