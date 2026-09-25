import * as React from 'react'
import { useForm } from 'react-hook-form'
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
} from '#/components/ui'
import type {
  CompanyRead,
  ErpIntegrationRead,
  ErpTypeRead,
  SpendTreeRead,
} from '#/lib/api/types'
import { findCountry } from '#/lib/format/countries'
import { currencyForCountry, findCurrency } from '#/lib/format/currencies'
import { CountryField } from '#/components/fields/country-field'
import { CurrencyField } from '#/components/fields/currency-field'
import { SubmitRow, useSettingsSubmit } from '#/components/settings/form'
import { defaultCredentials, toValues } from './company-values'
import type { CompanyFormValues } from './company-values'
import { ErpConnectionFields } from './erp-connection-fields'
import { SpendTreeField } from './spend-tree-field'

export function CompanyDialog({
  open,
  company,
  erpTypes,
  erpTypesLoading,
  companyIntegrations,
  spendTrees,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  /** The company being edited, or null when creating. */
  company: CompanyRead | null
  erpTypes: Array<ErpTypeRead>
  erpTypesLoading: boolean
  /** The organization's active trees; empty hides the picker entirely. */
  spendTrees: Array<SpendTreeRead>
  /** This company's integrations, most-connected first. Empty when creating. */
  companyIntegrations: Array<ErpIntegrationRead>
  onOpenChange: (open: boolean) => void
  onSubmit: (values: CompanyFormValues) => Promise<unknown>
}) {
  const integration = company ? companyIntegrations[0] : undefined
  const mode = !company ? 'create' : integration ? 'edit' : 'connect'
  const soleType = erpTypes.length === 1 ? erpTypes[0] : undefined
  const preselected = mode === 'create' ? soleType : undefined
  const form = useForm<CompanyFormValues>({
    defaultValues: {
      ...(company
        ? toValues(company)
        : {
            name: '',
            country_code: '',
            vat_number: '',
            base_currency: '',
            spend_tree_id: '',
          }),
      erp_type: integration?.erp_type ?? preselected?.erp_type ?? '',
      credentials: defaultCredentials(preselected),
      label: integration?.label ?? '',
      replaceCredentials: false,
    },
  })
  const submit = useSettingsSubmit()

  const countryCode = form.watch('country_code')
  const currencyTouched = form.formState.dirtyFields.base_currency
  React.useEffect(() => {
    if (mode !== 'create' || currencyTouched) {
      return
    }
    const implied = currencyForCountry(countryCode)
    if (implied) {
      form.setValue('base_currency', implied)
    }
  }, [countryCode, currencyTouched, mode, form])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{company ? 'Edit company' : 'Add company'}</DialogTitle>
          <DialogDescription>
            A company is a legal entity whose ERP data this workspace reports
            on.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            className="flex flex-col gap-4"
            onSubmit={submit({
              form,
              run: async (values) => {
                const result = await onSubmit(values)
                onOpenChange(false)
                return result
              },
              success: company ? 'Company updated' : 'Company added',
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
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="country_code"
                rules={{
                  validate: (value: string) =>
                    !value ||
                    findCountry(value) !== undefined ||
                    'Choose a country from the list.',
                }}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Country</FormLabel>
                    <FormControl>
                      <CountryField
                        value={field.value}
                        onChange={field.onChange}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="vat_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>VAT number</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="base_currency"
              rules={{
                required: 'Choose a reporting currency.',
                validate: (value: string) =>
                  findCurrency(value) !== undefined ||
                  'Choose a currency from the list.',
              }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Reporting currency</FormLabel>
                  <FormControl>
                    <CurrencyField
                      value={field.value}
                      onChange={field.onChange}
                    />
                  </FormControl>
                  <FormDescription>
                    Every figure for this company is shown in this currency.
                    Amounts posted in another are converted at the rate on the
                    day of the transaction.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            {spendTrees.length > 0 ? (
              <FormField
                control={form.control}
                name="spend_tree_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Spend tree</FormLabel>
                    <FormControl>
                      <SpendTreeField
                        value={field.value}
                        trees={spendTrees}
                        onChange={field.onChange}
                      />
                    </FormControl>
                    <FormDescription>
                      {mode === 'create' ? (
                        <>
                          The taxonomy this company&rsquo;s spend is categorized
                          into. Leave it on the default unless you have built
                          your own.
                        </>
                      ) : (
                        <>
                          Changing this keeps every category already assigned on
                          record, but lines whose category is not in the new
                          tree will be marked for review.
                        </>
                      )}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            ) : null}
            <ErpConnectionFields
              form={form}
              erpTypes={erpTypes}
              loading={erpTypesLoading}
              mode={mode}
              integration={integration}
              otherCount={Math.max(companyIntegrations.length - 1, 0)}
            />
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <SubmitRow
                form={form}
                label={company ? 'Save changes' : 'Add company'}
              />
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
