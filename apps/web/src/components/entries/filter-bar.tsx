import * as React from 'react'
import { X } from 'lucide-react'
import {
  Button,
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  DatePicker,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '#/components/ui'
import { LINE_ORIGINS } from '#/lib/entry-search'
import { fromIsoDate, humanizeKey, toIsoDate } from '#/lib/format/format'
import { CountryFlag } from '#/components/fields/country-flag'
import type {
  CompanyRead,
  EntryFilters,
  LineOrigin,
  VendorRead,
} from '#/lib/api/types'

/** Reader-facing labels for each line origin. */
const ORIGIN_LABELS: Record<LineOrigin, string> = {
  document_ai: 'From document',
  erp: 'From ERP',
  entry_fallback: 'From posting',
  human: 'Added by hand',
}

/** Shared width for every control in the bar. */
const CONTROL = 'w-44'

const ORIGIN_OPTIONS = LINE_ORIGINS.map((value) => ({
  value,
  label: ORIGIN_LABELS[value],
}))

/** A company picker row: country flag, then name. */
function CompanyOption({
  country,
  children,
}: {
  country: string | null
  children: React.ReactNode
}) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      {country ? (
        <CountryFlag country={country} />
      ) : (
        <span aria-hidden className="block size-5 shrink-0" />
      )}
      <span className="min-w-0">{children}</span>
    </span>
  )
}

/** Every entry status. */
const STATUSES = ['pending', 'posted', 'synced', 'failed'] as const

/** Value of the "no filter" option; the Select's own unset value is ''. */
const ALL = '__all__'
const REVIEW = 'needs_review'
const REVIEW_OPTIONS = [{ value: REVIEW, label: 'Needs review' }]

const STATUS_OPTIONS = STATUSES.map((value) => ({
  value,
  label: humanizeKey(value),
}))

export interface FilterBarProps {
  filters: EntryFilters
  companies: Array<CompanyRead>
  vendors: Array<VendorRead>
  entryTypes: Array<string>
  onChange: (changes: Partial<EntryFilters>) => void
  onClear: () => void
  onVendorSearch: (query: string) => void
}

export function FilterBar({
  filters,
  companies,
  vendors,
  entryTypes,
  onChange,
  onClear,
  onVendorSearch,
}: FilterBarProps) {
  const entryTypeOptions = React.useMemo(
    () => entryTypes.map((value) => ({ value, label: humanizeKey(value) })),
    [entryTypes],
  )

  const active = (
    [
      'company_id',
      'entry_type',
      'status',
      'vendor_id',
      'origin',
      'needs_review',
      'from',
      'to',
    ] as const
  ).some((key) => filters[key] !== undefined)
  const selectedVendor = vendors.find((v) => v.id === filters.vendor_id)

  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">
          Company
        </span>
        <Select
          value={filters.company_id ?? ''}
          onValueChange={(next: string | null) =>
            onChange({ company_id: next && next !== ALL ? next : undefined })
          }
        >
          <SelectTrigger className={CONTROL}>
            <SelectValue
              placeholder="All companies"
              items={companies.map((c) => ({ value: c.id, label: c.name }))}
            />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>
              <CompanyOption country={null}>All companies</CompanyOption>
            </SelectItem>
            {companies.map((company) => (
              <SelectItem key={company.id} value={company.id}>
                <CompanyOption country={company.country_code}>
                  {company.name}
                </CompanyOption>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">From</span>
        <DatePicker
          aria-label="From date"
          value={fromIsoDate(filters.from)}
          placeholder="Any date"
          onChange={(date) => onChange({ from: toIsoDate(date) })}
          className={CONTROL}
        />
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">To</span>
        <DatePicker
          aria-label="To date"
          value={fromIsoDate(filters.to)}
          placeholder="Any date"
          onChange={(date) => onChange({ to: toIsoDate(date) })}
          className={CONTROL}
        />
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">
          Entry type
        </span>
        <Select
          value={filters.entry_type ?? ''}
          onValueChange={(next: string | null) =>
            onChange({ entry_type: next && next !== ALL ? next : undefined })
          }
        >
          <SelectTrigger className={CONTROL}>
            <SelectValue placeholder="All types" items={entryTypeOptions} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All types</SelectItem>
            {entryTypeOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">
          Status
        </span>
        <Select
          value={filters.status ?? ''}
          onValueChange={(next: string | null) =>
            onChange({ status: next && next !== ALL ? next : undefined })
          }
        >
          <SelectTrigger className={CONTROL}>
            <SelectValue placeholder="Any status" items={STATUS_OPTIONS} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Any status</SelectItem>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">
          Line source
        </span>
        <Select
          value={filters.origin ?? ''}
          onValueChange={(next: string | null) =>
            onChange({
              origin: next && next !== ALL ? (next as LineOrigin) : undefined,
            })
          }
        >
          <SelectTrigger className={CONTROL}>
            <SelectValue placeholder="Any source" items={ORIGIN_OPTIONS} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Any source</SelectItem>
            {ORIGIN_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">
          Confidence
        </span>
        <Select
          value={filters.needs_review === true ? REVIEW : ''}
          onValueChange={(next: string | null) =>
            onChange({ needs_review: next === REVIEW ? true : undefined })
          }
        >
          <SelectTrigger className={CONTROL}>
            <SelectValue placeholder="Any confidence" items={REVIEW_OPTIONS} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Any confidence</SelectItem>
            <SelectItem value={REVIEW}>Needs review</SelectItem>
          </SelectContent>
        </Select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">
          Supplier
        </span>
        <Combobox
          items={vendors}
          value={selectedVendor}
          itemToStringLabel={(vendor: VendorRead) => vendor.name}
          isItemEqualToValue={(a: VendorRead, b: VendorRead) => a.id === b.id}
          onValueChange={(next: VendorRead | null) =>
            onChange({ vendor_id: next?.id })
          }
          onInputValueChange={onVendorSearch}
        >
          <ComboboxInput placeholder="All suppliers" className={CONTROL} />
          <ComboboxContent>
            <ComboboxEmpty>No suppliers found.</ComboboxEmpty>
            <ComboboxList>
              {(vendor: VendorRead) => (
                <ComboboxItem key={vendor.id} value={vendor}>
                  {vendor.name}
                </ComboboxItem>
              )}
            </ComboboxList>
          </ComboboxContent>
        </Combobox>
      </label>

      {active ? (
        <Button variant="ghost" onClick={onClear}>
          <X className="size-4" />
          Clear filters
        </Button>
      ) : null}
    </div>
  )
}
