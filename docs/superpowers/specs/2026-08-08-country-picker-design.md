# Country picker for `Company.country_code`

## Problem

An audit of every selection control in the frontend found no native `<select>`
anywhere and one genuine outlier: the company create/edit dialog took
`country_code` as a free-text `Input` guarded only by `/^[A-Za-z]{0,2}$/`.

That is a choice from a closed set (ISO 3166-1 alpha-2) rendered as a text box,
and it sat directly above `base_currency`, which is a searchable `Combobox` —
two adjacent code fields with two interaction models. Three consequences:

- The regex checked shape, not membership, so `ZZ` and `qq` saved cleanly.
- Nothing normalized case, so `dk` was stored and displayed as `dk` in the
  companies table.
- The value feeds `currencyForCountry()` to pre-select the reporting currency, so
  a typo silently produced no suggestion with nothing explaining why.

Currency needed no work: `CurrencyField` is already a combobox and is the only
place a currency is picked.

## Design

### `lib/countries.ts`

Mirrors `lib/currencies.ts`. All **249 officially assigned ISO 3166-1 alpha-2
codes** with CLDR English names, so no customer's country is unrepresentable.
`St.` is spelled out as `Saint` and `&` as `and` so either spelling matches.

Kept separate from `currencies.ts` deliberately: that module's `country` field
names the *issuer* of a currency and carries the non-ISO `EU`, which is a
different question from where a company is registered. `currencyForCountry`
remains there and is untouched.

Exports `COUNTRIES`, `findCountry` (trims and uppercases, so `dk` resolves),
`countryLabel` (`DK — Denmark`) and `foldForSearch` (NFD + diacritic strip).

### `components/settings/country-field.tsx`

A near-copy of `CurrencyField`: `Combobox` over `COUNTRIES`, controlled
`inputValue` synced from the incoming value by effect — Base UI owns the input's
text, so a value set from outside would otherwise leave the field showing
something other than the form's value.

Two deviations from `CurrencyField`:

- **Diacritic-insensitive filtering** via `filteredItems`. Base UI's built-in
  filter compares the raw label, which leaves `Åland`, `Côte d'Ivoire` and
  `Curaçao` reachable only by code or by typing the accent.
- **An unresolved-code state.** The field was free text before, so anything could
  be stored. A code that names no country renders as `Unknown code: ZZ` behind a
  warning triangle rather than blanking, because silently dropping what is stored
  would overwrite it on the next save with no trace. A `validate` rule on the
  form field rejects it: *"Choose a country from the list."* Empty still passes —
  the field stays optional.

### Normalization

`onChange` always emits the canonical uppercase code, so the only way a
non-canonical value enters the form is an existing company opened for editing.
`toValues()` canonicalizes there — one place. `before` and `after` then agree, so
merely opening a company stored as `dk` does not register as an edit.

### `CurrencyFlag` → `CountryFlag`

The component was always keyed on country and now has two callers, so it is
renamed (`currency-flag.tsx` → `country-flag.tsx`). Its lettered-code fallback
changes status: with 31 flag assets against 249 countries it is now the common
case in the country list, not the edge case.

**No new flag artwork.** Adding ~218 SVGs to dress a picker is not worth the
bytes or the maintenance.

## Testing

- `lib/countries.test.ts` — exactly 249 unique well-formed codes; `EU`, `UK`,
  `XK`, `AN`, `SU`, `ZZ` excluded; `dk` and ` Dk ` resolve; diacritic folding.
- `components/settings/country-field.test.tsx` — stored code displays its
  country; lowercase resolves; `ZZ` surfaces as unknown; picking emits uppercase;
  search by code, by name, and by unaccented name; a country with no currency and
  no flag (Kenya) is still selectable.
- `companies-panel.test.tsx` — the two currency-pre-selection tests drove the
  country with `fireEvent.change` on a text input and now select from the
  combobox via a `chooseCountry` helper. The assertions are unchanged.

## Out of scope

The companies table still renders the bare code. Showing the name there is a
separate call.
