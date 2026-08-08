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
import type { Country } from '#/lib/countries'
import { COUNTRIES, countryLabel, findCountry, foldForSearch } from '#/lib/countries'
import { CountryFlag } from './country-flag'

/**
 * One row: flag, code, name. The same split as the currency list — the code is
 * what gets stored, so it takes the display face; the name is what the user
 * actually reads, and stays quiet beside it.
 */
function CountryRow({ country }: { country: Country }) {
  return (
    <span className="flex min-w-0 flex-1 items-center gap-2.5">
      <CountryFlag country={country.code} />
      <span className="font-display font-semibold tracking-tight text-foreground">
        {country.code}
      </span>
      <span className="min-w-0 truncate text-muted-foreground">{country.name}</span>
    </span>
  )
}

/**
 * Diacritic-insensitive contains matching. Base UI's built-in filter compares
 * the raw label, which leaves `Åland`, `Côte d’Ivoire` and `Curaçao` reachable
 * only by their code or by typing the accent.
 */
function matches(country: Country, query: string): boolean {
  return foldForSearch(countryLabel(country)).includes(foldForSearch(query))
}

/**
 * Picks the country a company is registered in.
 *
 * A combobox rather than the free-text box this replaced: the value is an ISO
 * 3166-1 code from a closed set, it is displayed back to the user in the
 * companies table, and it pre-selects the reporting currency — three reasons a
 * typo should not be expressible.
 */
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
  // A code that resolves to nothing: the field was free text before this, so
  // anything could have been saved. Surfaced rather than blanked — silently
  // dropping what is stored would overwrite it on the next save with no trace.
  const unresolved = value.trim() !== '' && selected === undefined

  // Base UI owns the input's text, so a value set from outside — an existing
  // company opened for editing — would otherwise leave the field showing
  // something other than the form's value. Controlling both keeps them honest.
  const [inputValue, setInputValue] = React.useState(() =>
    selected ? countryLabel(selected) : unresolved ? `Unknown code: ${value}` : '',
  )
  React.useEffect(() => {
    setInputValue(
      selected ? countryLabel(selected) : unresolved ? `Unknown code: ${value}` : '',
    )
  }, [selected, unresolved, value])

  const filteredItems = React.useMemo(() => {
    // While the input still shows the selection's own label there is nothing to
    // filter by — the user has not typed yet, and matching on it would narrow
    // the list to the one row already chosen.
    if (!inputValue.trim() || inputValue === (selected && countryLabel(selected))) {
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
      {/* The flag sits in the field itself, the same as the currency picker
          above it — two adjacent code fields that behaved differently were the
          reason this control was rebuilt, so they should now also look alike. */}
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
              // Named explicitly: the row is three adjacent spans, and the
              // computed name runs them together as "DKDenmark".
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
