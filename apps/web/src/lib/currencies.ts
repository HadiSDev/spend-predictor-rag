/**
 * Every ISO 4217 currency, with the ones the ECB publishes daily rates for
 * marked.
 *
 * The list is built from `Intl` rather than hand-maintained: the runtime
 * already ships ISO 4217, its English names and its symbols, so a vendored
 * table could only be the same data with a staleness problem. It is also how
 * `CurrencyInput` and `formatMoney` render money, which is what stops a picker
 * and the figure beside it disagreeing about how a currency is written.
 *
 * **All of them are offered, and that is a change.** The list used to be the
 * 31 ECB-rate currencies only, on the reasoning that offering one we cannot
 * convert lets a user pick a setting that leaves every figure unconverted.
 * That reasoning holds for a company's *base* currency and not for an
 * invoice's: a Kenyan supplier billing KES is a fact, and refusing to record it
 * does not make it untrue — the invoice simply stores unconverted, which the
 * product already shows honestly. So the restriction becomes information:
 * `hasRates` says whether a historical rate can be resolved, and a caller that
 * cares can say so.
 */
export interface Currency {
  code: string
  name: string
  /**
   * ISO 3166-1 alpha-2 of the issuing country, or `EU` for the euro. Drives the
   * flag; presentation only, and never leaves the client.
   */
  country: string
  /** How this currency is written where it is spent — `kr`, `€`, `zł`. */
  symbol: string
  /**
   * The ECB publishes a daily reference rate for this currency, so an amount in
   * it can be converted at the rate in force on its own date. False means the
   * amount is recorded faithfully and reported unconverted.
   */
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

/**
 * A currency's issuing country, for the flag.
 *
 * ISO 4217 builds almost every code from its country's alpha-2 plus a letter —
 * `DKK` from `DK`, `KES` from `KE` — so the first two letters are the answer
 * often enough to be the rule. `EUR` gives `EU`, which is exactly right and is
 * why the euro needs no special case. Supranational codes starting `X` (`XOF`,
 * `XCD`) have no country and fall through to the lettered chip, which is what
 * that fallback is for.
 */
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
  const codes = new Set<string>([...ECB_RATE_CURRENCIES, ...Intl.supportedValuesOf('currency')])
  const build = (code: string): Currency => ({
    code,
    name: nameOf(display, code),
    country: issuerOf(code),
    symbol: symbolOf(code),
    hasRates: rated.has(code),
  })

  // Convertible first, in their curated order — those are what nearly every
  // customer picks, and burying DKK at position 40 of an alphabetical list
  // would make the common case the slow one. The rest follow alphabetically,
  // which is the only order a reader can predict for 130 unfamiliar codes.
  const rest = [...codes].filter((code) => !rated.has(code)).sort()
  return [...ECB_RATE_CURRENCIES, ...rest].map(build)
}

export const CURRENCIES: Array<Currency> = buildCurrencies()

/** Only the currencies an amount can actually be converted from. */
export const CONVERTIBLE_CURRENCIES: Array<Currency> = CURRENCIES.filter((c) => c.hasRates)

const BY_CODE = new Map(CURRENCIES.map((c) => [c.code, c]))

/** The currency for a code, or undefined for one that is not a currency. */
export function findCurrency(code: string | null | undefined): Currency | undefined {
  return code ? BY_CODE.get(code.toUpperCase()) : undefined
}

/** `DKK — Danish Krone`, so a user picks a currency rather than typing a code. */
export function currencyLabel(currency: Currency): string {
  return `${currency.code} — ${currency.name}`
}

/**
 * The currency a country most likely reports in. Used only to *pre-select* a
 * value the user can change — a Danish subsidiary reporting in EUR is ordinary,
 * so this must never be treated as the answer.
 */
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
  // The euro area.
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

export function currencyForCountry(countryCode: string | null | undefined): string | undefined {
  return countryCode ? COUNTRY_CURRENCY[countryCode.trim().toUpperCase()] : undefined
}
