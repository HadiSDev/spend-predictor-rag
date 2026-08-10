import * as React from 'react'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '#/components/ui'
import { CountryFlag } from '#/components/settings/country-flag'
import { foldForSearch } from '#/lib/countries'
import type { VendorRead } from '#/lib/types'

/** One row: the supplier's name, with its country beside it. Two suppliers can
 *  share a name across borders, and the country is what tells them apart. */
function VendorRow({ vendor }: { vendor: VendorRead }) {
  return (
    <span className="flex min-w-0 flex-1 items-center gap-2.5">
      {vendor.country_code ? <CountryFlag country={vendor.country_code} /> : null}
      <span className="min-w-0 truncate text-foreground">{vendor.name}</span>
      {vendor.vat_number ? (
        <span className="shrink-0 text-xs text-muted-foreground">{vendor.vat_number}</span>
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

/**
 * Picks which supplier an invoice points at.
 *
 * A combobox over the organization's known suppliers rather than a text box,
 * for the same reason a line's category is chosen from the tree and never
 * typed: the stored value is a foreign key, and a typed name would either
 * resolve to nothing or, worse, to a supplier that only looks right. Vendor
 * spend is aggregated by this id, so a wrong one moves money.
 *
 * Correcting the supplier's *details* is a different action, and lives beside
 * this field: those are invoice-scoped and never touch the shared catalog.
 */
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

  // Base UI owns the input's text, so a value set from outside — a different
  // invoice opened in the panel — would otherwise leave the field showing the
  // previous supplier. Controlling both keeps them honest.
  const [inputValue, setInputValue] = React.useState(() => selected?.name ?? '')
  React.useEffect(() => {
    setInputValue(selected?.name ?? '')
  }, [selected])

  const items = React.useMemo(() => {
    if (!vendors) return []
    // While the input still shows the selection's own name there is nothing to
    // filter by — the user has not typed yet, and matching on it would narrow
    // the list to the one supplier already chosen.
    const query = inputValue.trim()
    if (query === '' || query === selected?.name) return vendors
    return vendors.filter((v) => matches(v, query))
  }, [vendors, inputValue, selected])

  // No list yet is not the same as an empty list. Rendering a picker that can
  // only say "no suppliers" would read as "this organization has none", when
  // the request simply has not landed.
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
      <ComboboxInput id={id} aria-label="Supplier" placeholder="Search suppliers" />
      <ComboboxContent>
        <ComboboxEmpty>No supplier matches that.</ComboboxEmpty>
        <ComboboxList>
          {(vendor: VendorRead) => (
            <ComboboxItem
              key={vendor.id}
              value={vendor}
              // Named explicitly: the row is adjacent spans, and the computed
              // name runs them together as "Nordic Supplies ApSDK99999999".
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
