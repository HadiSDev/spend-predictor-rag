import * as React from 'react'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '#/components/ui'
import type { Currency } from '#/lib/currencies'
import { CURRENCIES, currencyLabel, findCurrency } from '#/lib/currencies'
import { CountryFlag } from './country-flag'

/**
 * One row in the list: coin, code, name, symbol.
 *
 * The weight split is the point. The code is what the user is actually
 * choosing, so it takes the display face and the ink; the country name is
 * context and stays quiet; the symbol sits right-aligned as a column, which is
 * what turns a list of sentences into something scannable.
 */
function CurrencyRow({ currency }: { currency: Currency }) {
  return (
    <span className="flex min-w-0 flex-1 items-center gap-2.5">
      <CountryFlag country={currency.country} />
      <span className="font-display font-semibold tracking-tight text-foreground">
        {currency.code}
      </span>
      <span className="min-w-0 truncate text-muted-foreground">{currency.name}</span>
      <span className="ml-auto pl-3 text-xs text-subtle-foreground tabular-nums">
        {currency.symbol}
      </span>
    </span>
  )
}

/**
 * Picks a currency: a company's reporting currency, or the one an invoice was
 * denominated in.
 *
 * Searchable and labelled `DKK — Danish Krone` rather than a bare code. A code
 * is three letters a reviewer has to already know, and the two questions this
 * answers — "which currency is this?" and "is DKK the one I mean?" — are both
 * easier against a name and a flag.
 *
 * Replaces a free-text box on the invoice header, where anything at all could
 * be typed. A currency that is not a real ISO 4217 code converts against
 * nothing: `FxService` resolves no rate for it, so the invoice silently stores
 * unconverted and reports as spend in a currency no report can group.
 */
export function CurrencyField({
  value,
  onChange,
  disabled = false,
  id,
  // The label is the caller's, because this is no longer only a settings
  // control: on an invoice it names the money the document was written in, not
  // the currency the company reports in, and announcing the wrong one is worse
  // than announcing nothing.
  'aria-label': ariaLabel = 'Reporting currency',
}: {
  value: string
  onChange: (code: string) => void
  disabled?: boolean
  id?: string
  'aria-label'?: string
}) {
  const selected = findCurrency(value)
  // The input's text is Base UI's own state, so a value set from outside — the
  // country pre-selection — would otherwise change the form without changing
  // what the user sees. Controlling both keeps the two honest.
  const [inputValue, setInputValue] = React.useState(selected ? currencyLabel(selected) : '')
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
      {/* The chosen currency's flag sits in the field itself: without it the
          control is a line of grey text among other lines of grey text, and the
          one setting that colours every figure in the product looks like the
          least important field on the form. */}
      <ComboboxInput
        id={id}
        aria-label={ariaLabel}
        placeholder="Search currencies"
        startAdornment={selected ? <CountryFlag country={selected.country} /> : null}
        // On the wrapper, but form controls inherit weight under Tailwind's
        // preflight, so the chosen currency still reads bolder than the
        // placeholder — which is the whole point of setting it.
        className={selected ? 'font-medium' : undefined}
      />
      <ComboboxContent>
        <ComboboxEmpty>No currencies found.</ComboboxEmpty>
        <ComboboxList>
          {(currency: Currency) => (
            <ComboboxItem
              key={currency.code}
              value={currency}
              // Named explicitly: the row is four adjacent spans, and the
              // computed name runs them together as "DKKDanish Kronekr".
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
