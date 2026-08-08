/**
 * ISO 4217 currencies a company can report in, plus the country → currency
 * mapping used to pre-select one.
 *
 * Deliberately not the full ISO list: these are the currencies the ECB
 * publishes daily reference rates for, plus EUR itself. Offering a currency we
 * cannot get a historical rate for would let a user pick a setting that leaves
 * every figure unconverted.
 */
export interface Currency {
  code: string
  name: string
  /**
   * ISO 3166-1 alpha-2 of the issuing country, or `EU` for the euro. Drives the
   * flag; it is presentation only and never leaves the client.
   */
  country: string
  /** How this currency is written where it is spent — `kr`, `€`, `zł`. */
  symbol: string
}

export const CURRENCIES: Array<Currency> = [
  { code: 'EUR', country: 'EU', symbol: '€', name: 'Euro' },
  { code: 'DKK', country: 'DK', symbol: 'kr', name: 'Danish Krone' },
  { code: 'SEK', country: 'SE', symbol: 'kr', name: 'Swedish Krona' },
  { code: 'NOK', country: 'NO', symbol: 'kr', name: 'Norwegian Krone' },
  { code: 'GBP', country: 'GB', symbol: '£', name: 'Pound Sterling' },
  { code: 'USD', country: 'US', symbol: '$', name: 'US Dollar' },
  { code: 'CHF', country: 'CH', symbol: 'Fr', name: 'Swiss Franc' },
  { code: 'PLN', country: 'PL', symbol: 'zł', name: 'Polish Zloty' },
  { code: 'CZK', country: 'CZ', symbol: 'Kč', name: 'Czech Koruna' },
  { code: 'HUF', country: 'HU', symbol: 'Ft', name: 'Hungarian Forint' },
  { code: 'RON', country: 'RO', symbol: 'lei', name: 'Romanian Leu' },
  { code: 'BGN', country: 'BG', symbol: 'лв', name: 'Bulgarian Lev' },
  { code: 'ISK', country: 'IS', symbol: 'kr', name: 'Icelandic Krona' },
  { code: 'TRY', country: 'TR', symbol: '₺', name: 'Turkish Lira' },
  { code: 'CAD', country: 'CA', symbol: '$', name: 'Canadian Dollar' },
  { code: 'AUD', country: 'AU', symbol: '$', name: 'Australian Dollar' },
  { code: 'NZD', country: 'NZ', symbol: '$', name: 'New Zealand Dollar' },
  { code: 'JPY', country: 'JP', symbol: '¥', name: 'Japanese Yen' },
  { code: 'CNY', country: 'CN', symbol: '¥', name: 'Chinese Yuan Renminbi' },
  { code: 'HKD', country: 'HK', symbol: '$', name: 'Hong Kong Dollar' },
  { code: 'SGD', country: 'SG', symbol: '$', name: 'Singapore Dollar' },
  { code: 'KRW', country: 'KR', symbol: '₩', name: 'South Korean Won' },
  { code: 'INR', country: 'IN', symbol: '₹', name: 'Indian Rupee' },
  { code: 'BRL', country: 'BR', symbol: 'R$', name: 'Brazilian Real' },
  { code: 'MXN', country: 'MX', symbol: '$', name: 'Mexican Peso' },
  { code: 'ZAR', country: 'ZA', symbol: 'R', name: 'South African Rand' },
  { code: 'ILS', country: 'IL', symbol: '₪', name: 'Israeli Shekel' },
  { code: 'PHP', country: 'PH', symbol: '₱', name: 'Philippine Peso' },
  { code: 'IDR', country: 'ID', symbol: 'Rp', name: 'Indonesian Rupiah' },
  { code: 'MYR', country: 'MY', symbol: 'RM', name: 'Malaysian Ringgit' },
  { code: 'THB', country: 'TH', symbol: '฿', name: 'Thai Baht' },
]

const BY_CODE = new Map(CURRENCIES.map((c) => [c.code, c]))

/** The currency for a code, or undefined for one we do not offer. */
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
