import * as React from 'react'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '#/components/ui'
import { CountryFlag } from '#/components/fields/country-flag'
import { foldForSearch } from '#/lib/format/countries'
import type { VendorRead } from '#/lib/api/types'

/** One supplier option: name, country flag and VAT number. */
function VendorRow({ vendor }: { vendor: VendorRead }) {
  return (
    <span className="flex min-w-0 flex-1 items-center gap-2.5">
      {vendor.country_code ? (
        <CountryFlag country={vendor.country_code} />
      ) : null}
      <span className="min-w-0 truncate text-foreground">{vendor.name}</span>
      {vendor.vat_number ? (
        <span className="shrink-0 text-xs text-muted-foreground">
          {vendor.vat_number}
        </span>
      ) : null}
    </span>
  )
}

function matches(vendor: VendorRead, query: string): boolean {
  const haystack = [vendor.name, vendor.vat_number, vendor.country_code]
    .filter(Boolean)
    .join(' ')
  return foldForSearch(haystack).includes(foldForSearch(query))
}

/** Picks which supplier an invoice points at. */
export function VendorField({
  value,
  vendors,
  onChange,
  id,
}: {
  value: string
  vendors: Array<VendorRead> | null
  onChange: (vendorId: string) => void
  id?: string
}) {
  const selected = vendors?.find((v) => v.id === value)

  const [inputValue, setInputValue] = React.useState(() => selected?.name ?? '')
  React.useEffect(() => {
    setInputValue(selected?.name ?? '')
  }, [selected])

  const items = React.useMemo(() => {
    if (!vendors) {
      return []
    }
    const query = inputValue.trim()
    if (query === '' || query === selected?.name) {
      return vendors
    }
    return vendors.filter((v) => matches(v, query))
  }, [vendors, inputValue, selected])

  if (vendors === null) {
    return (
      <span className="text-sm text-muted-foreground">
        {selected?.name ?? 'Loading suppliers…'}
      </span>
    )
  }

  return (
    <Combobox
      items={vendors}
      filteredItems={items}
      value={selected}
      inputValue={inputValue}
      itemToStringLabel={(vendor: VendorRead) => vendor.name}
      isItemEqualToValue={(a: VendorRead, b: VendorRead) => a.id === b.id}
      onInputValueChange={(next: string) => setInputValue(next)}
      onValueChange={(next: VendorRead | null) => onChange(next?.id ?? '')}
    >
      <ComboboxInput
        id={id}
        aria-label="Supplier"
        placeholder="Search suppliers"
      />
      <ComboboxContent>
        <ComboboxEmpty>No supplier matches that.</ComboboxEmpty>
        <ComboboxList>
          {(vendor: VendorRead) => (
            <ComboboxItem
              key={vendor.id}
              value={vendor}
              aria-label={vendor.name}
              className="gap-0 py-2"
            >
              <VendorRow vendor={vendor} />
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
