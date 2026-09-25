/** Every ISO 4217 currency, with the ones the ECB publishes daily rates for marked. */
export interface Currency {
  code: string
  name: string
  /** ISO 3166-1 alpha-2 of the issuing country, or `EU` for the euro. */
  country: string
  /** How this currency is written where it is spent — `kr`, `€`, `zł`. */
  symbol: string
  /** The ECB publishes a daily reference rate for this currency. */
  hasRates: boolean
}

/** The 31 the ECB publishes daily reference rates for, most-used first. */
const ECB_RATE_CURRENCIES: Array<string> = [
  'EUR',
  'DKK',
  'SEK',
  'NOK',
  'GBP',
  'USD',
  'CHF',
  'PLN',
  'CZK',
  'HUF',
  'RON',
  'BGN',
  'ISK',
  'TRY',
  'CAD',
  'AUD',
  'NZD',
  'JPY',
  'CNY',
  'HKD',
  'SGD',
  'KRW',
  'INR',
  'BRL',
  'MXN',
  'ZAR',
  'ILS',
  'PHP',
  'IDR',
  'MYR',
  'THB',
]

/** A currency's issuing country, for the flag. */
function issuerOf(code: string): string {
  return code.slice(0, 2).toUpperCase()
}

function symbolOf(code: string): string {
  try {
    const parts = new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency: code,
      currencyDisplay: 'narrowSymbol',
    }).formatToParts(0)
    return parts.find((part) => part.type === 'currency')?.value ?? code
  } catch {
    return code
  }
}

function nameOf(display: Intl.DisplayNames, code: string): string {
  try {
    return display.of(code) ?? code
  } catch {
    return code
  }
}

function buildCurrencies(): Array<Currency> {
  const display = new Intl.DisplayNames(['en'], { type: 'currency' })
  const rated = new Set(ECB_RATE_CURRENCIES)
  const codes = new Set<string>([
    ...ECB_RATE_CURRENCIES,
    ...Intl.supportedValuesOf('currency'),
  ])
  const build = (code: string): Currency => ({
    code,
    name: nameOf(display, code),
    country: issuerOf(code),
    symbol: symbolOf(code),
    hasRates: rated.has(code),
  })

  const rest = [...codes].filter((code) => !rated.has(code)).sort()
  return [...ECB_RATE_CURRENCIES, ...rest].map(build)
}

export const CURRENCIES: Array<Currency> = buildCurrencies()

/** Only the currencies an amount can actually be converted from. */
export const CONVERTIBLE_CURRENCIES: Array<Currency> = CURRENCIES.filter(
  (c) => c.hasRates,
)

const BY_CODE = new Map(CURRENCIES.map((c) => [c.code, c]))

/** The currency for a code, or undefined for one that is not a currency. */
export function findCurrency(
  code: string | null | undefined,
): Currency | undefined {
  return code ? BY_CODE.get(code.toUpperCase()) : undefined
}

/** A currency's `DKK — Danish Krone` label. */
export function currencyLabel(currency: Currency): string {
  return `${currency.code} — ${currency.name}`
}

/** The currency a country most likely reports in. */
const COUNTRY_CURRENCY: Record<string, string> = {
  DK: 'DKK',
  SE: 'SEK',
  NO: 'NOK',
  IS: 'ISK',
  GB: 'GBP',
  US: 'USD',
  CH: 'CHF',
  PL: 'PLN',
  CZ: 'CZK',
  HU: 'HUF',
  RO: 'RON',
  BG: 'BGN',
  TR: 'TRY',
  CA: 'CAD',
  AU: 'AUD',
  NZ: 'NZD',
  JP: 'JPY',
  CN: 'CNY',
  IN: 'INR',
  AT: 'EUR',
  BE: 'EUR',
  CY: 'EUR',
  DE: 'EUR',
  EE: 'EUR',
  ES: 'EUR',
  FI: 'EUR',
  FR: 'EUR',
  GR: 'EUR',
  HR: 'EUR',
  IE: 'EUR',
  IT: 'EUR',
  LT: 'EUR',
  LU: 'EUR',
  LV: 'EUR',
  MT: 'EUR',
  NL: 'EUR',
  PT: 'EUR',
  SI: 'EUR',
  SK: 'EUR',
}

export function currencyForCountry(
  countryCode: string | null | undefined,
): string | undefined {
  return countryCode
    ? COUNTRY_CURRENCY[countryCode.trim().toUpperCase()]
    : undefined
}
