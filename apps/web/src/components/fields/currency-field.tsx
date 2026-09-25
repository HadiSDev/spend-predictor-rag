import * as React from 'react'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '#/components/ui'
import type { Currency } from '#/lib/format/currencies'
import {
  CURRENCIES,
  currencyLabel,
  findCurrency,
} from '#/lib/format/currencies'
import { CountryFlag } from './country-flag'

/** A currency option row: flag, code, name and symbol. */
function CurrencyRow({ currency }: { currency: Currency }) {
  return (
    <span className="flex min-w-0 flex-1 items-center gap-2.5">
      <CountryFlag country={currency.country} />
      <span className="font-display font-semibold tracking-tight text-foreground">
        {currency.code}
      </span>
      <span className="min-w-0 truncate text-muted-foreground">
        {currency.name}
      </span>
      <span className="ml-auto pl-3 text-xs text-subtle-foreground tabular-nums">
        {currency.symbol}
      </span>
    </span>
  )
}

/** Searchable combobox for picking an ISO 4217 currency. */
export function CurrencyField({
  value,
  onChange,
  disabled = false,
  id,
  'aria-label': ariaLabel = 'Reporting currency',
}: {
  value: string
  onChange: (code: string) => void
  disabled?: boolean
  id?: string
  'aria-label'?: string
}) {
  const selected = findCurrency(value)
  const [inputValue, setInputValue] = React.useState(
    selected ? currencyLabel(selected) : '',
  )
  React.useEffect(() => {
    setInputValue(selected ? currencyLabel(selected) : '')
  }, [selected])

  return (
    <Combobox
      items={CURRENCIES}
      value={selected}
      inputValue={inputValue}
      disabled={disabled}
      itemToStringLabel={currencyLabel}
      isItemEqualToValue={(a: Currency, b: Currency) => a.code === b.code}
      onInputValueChange={(next: string) => setInputValue(next)}
      onValueChange={(next: Currency | null) => onChange(next?.code ?? '')}
    >
      <ComboboxInput
        id={id}
        aria-label={ariaLabel}
        placeholder="Search currencies"
        startAdornment={
          selected ? <CountryFlag country={selected.country} /> : null
        }
        className={selected ? 'font-medium' : undefined}
      />
      <ComboboxContent>
        <ComboboxEmpty>No currencies found.</ComboboxEmpty>
        <ComboboxList>
          {(currency: Currency) => (
            <ComboboxItem
              key={currency.code}
              value={currency}
              aria-label={currencyLabel(currency)}
              className="gap-0 py-2"
            >
              <CurrencyRow currency={currency} />
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
