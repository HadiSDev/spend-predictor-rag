/** Response types mirroring the web API's Pydantic schemas (`web_api/schemas.py`). */

/** Decimal fields arrive as strings (Pydantic JSON) or numbers; coerce on use. */
export type Money = string | number

/** `GET /users/me` — the current principal. */
export interface UserRead {
  id: string
  email: string
  name: string
  role: string
  is_system_admin: boolean
  organization_id: string
}

/** Envelope for small aggregate reports (`Report[T]`). */
export interface Report<T> {
  rows: Array<T>
}

/** Row of `GET /reports/entries-summary`. */
export interface EntrySummaryRow {
  entry_type: string
  currency: string | null
  debit_total: Money
  credit_total: Money
  net: Money
  count: number
}

/** Row of `GET /reports/spend-by-category`. */
export interface CategorySpendRow {
  level_2: string | null
  level_3: string | null
  currency: string | null
  amount_total: Money
  count: number
}

/** Row of `GET /reports/spend-by-vendor`. */
export interface VendorSpendRow {
  vendor_id: string
  vendor_name: string
  currency: string | null
  amount_total: Money
  count: number
}
