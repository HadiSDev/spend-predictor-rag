import * as React from 'react'
import { TriangleAlert } from 'lucide-react'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '#/components/ui'
import type { Country } from '#/lib/format/countries'
import {
  COUNTRIES,
  countryLabel,
  findCountry,
  foldForSearch,
} from '#/lib/format/countries'
import { CountryFlag } from './country-flag'

/** A country option row: flag, code and name. */
function CountryRow({ country }: { country: Country }) {
  return (
    <span className="flex min-w-0 flex-1 items-center gap-2.5">
      <CountryFlag country={country.code} />
      <span className="font-display font-semibold tracking-tight text-foreground">
        {country.code}
      </span>
      <span className="min-w-0 truncate text-muted-foreground">
        {country.name}
      </span>
    </span>
  )
}

/** Diacritic-insensitive match of a country against a search query. */
function matches(country: Country, query: string): boolean {
  return foldForSearch(countryLabel(country)).includes(foldForSearch(query))
}

/** Combobox for picking a company's country by ISO 3166-1 code. */
export function CountryField({
  value,
  onChange,
  disabled = false,
  id,
}: {
  value: string
  onChange: (code: string) => void
  disabled?: boolean
  id?: string
}) {
  const selected = findCountry(value)
  const unresolved = value.trim() !== '' && selected === undefined

  const [inputValue, setInputValue] = React.useState(() =>
    selected
      ? countryLabel(selected)
      : unresolved
        ? `Unknown code: ${value}`
        : '',
  )
  React.useEffect(() => {
    setInputValue(
      selected
        ? countryLabel(selected)
        : unresolved
          ? `Unknown code: ${value}`
          : '',
    )
  }, [selected, unresolved, value])

  const filteredItems = React.useMemo(() => {
    const isShowingSelection =
      selected !== undefined && inputValue === countryLabel(selected)
    if (!inputValue.trim() || isShowingSelection) {
      return COUNTRIES
    }
    return COUNTRIES.filter((country) => matches(country, inputValue))
  }, [inputValue, selected])

  return (
    <Combobox
      items={COUNTRIES}
      filteredItems={filteredItems}
      value={selected}
      inputValue={inputValue}
      disabled={disabled}
      itemToStringLabel={countryLabel}
      isItemEqualToValue={(a: Country, b: Country) => a.code === b.code}
      onInputValueChange={(next: string) => setInputValue(next)}
      onValueChange={(next: Country | null) => onChange(next?.code ?? '')}
    >
      <ComboboxInput
        id={id}
        aria-label="Country"
        placeholder="Search countries"
        startAdornment={
          selected ? (
            <CountryFlag country={selected.code} />
          ) : unresolved ? (
            <TriangleAlert className="size-4 text-warning" aria-hidden />
          ) : null
        }
      />
      <ComboboxContent>
        <ComboboxEmpty>No countries found.</ComboboxEmpty>
        <ComboboxList>
          {(country: Country) => (
            <ComboboxItem
              key={country.code}
              value={country}
              aria-label={countryLabel(country)}
              className="gap-0 py-2"
            >
              <CountryRow country={country} />
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
