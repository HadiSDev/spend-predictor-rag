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
import type { CompanyRead, EntryFilters, LineOrigin, VendorRead } from '#/lib/types'

/** What each provenance means to a reader, who does not think in enum values. */
const ORIGIN_LABELS: Record<LineOrigin, string> = {
  document_ai: 'Read from document',
  erp: 'From the ERP',
  entry_fallback: 'Standing in for a posting',
}

/** The domain's fixed set. Kept explicit so a status with no rows yet — the
 *  failed ones especially — never vanishes from the filter. */
const STATUSES = ['pending', 'posted', 'synced', 'failed'] as const

/**
 * Value of the "no filter" option. It cannot be `''` — that is the Select's
 * unset value, and an item carrying it can never be pressed to clear. An unset
 * filter is therefore `''` (so the trigger falls back to the placeholder) while
 * the option that clears it carries this sentinel.
 */
const ALL = '__all__'

/** `<input type=date>`-shaped string, which is also what the API takes. */
function toIsoDate(date: Date | undefined): string | undefined {
  if (!date) return undefined
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

function fromIsoDate(value: string | undefined): Date | undefined {
  if (!value) return undefined
  const parsed = new Date(`${value}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? undefined : parsed
}

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
  // `page` is not a filter; it should not light up the clear control.
  const active = (
    ['company_id', 'entry_type', 'status', 'vendor_id', 'origin', 'from', 'to'] as const
  ).some(
    (key) => filters[key] !== undefined,
  )
  const selectedVendor = vendors.find((v) => v.id === filters.vendor_id)

  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">Company</span>
        <Select
          value={filters.company_id ?? ''}
          onValueChange={(next: string | null) =>
            onChange({ company_id: next && next !== ALL ? next : undefined })
          }
        >
          <SelectTrigger className="w-48">
            <SelectValue
              placeholder="All companies"
              items={companies.map((c) => ({ value: c.id, label: c.name }))}
            />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All companies</SelectItem>
            {companies.map((company) => (
              <SelectItem key={company.id} value={company.id}>
                {company.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">From</span>
        <DatePicker
          value={fromIsoDate(filters.from)}
          placeholder="Any date"
          onChange={(date) => onChange({ from: toIsoDate(date) })}
          className="w-40"
        />
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">To</span>
        <DatePicker
          value={fromIsoDate(filters.to)}
          placeholder="Any date"
          onChange={(date) => onChange({ to: toIsoDate(date) })}
          className="w-40"
        />
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">Entry type</span>
        <Select
          value={filters.entry_type ?? ''}
          onValueChange={(next: string | null) =>
            onChange({ entry_type: next && next !== ALL ? next : undefined })
          }
        >
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All types</SelectItem>
            {entryTypes.map((type) => (
              <SelectItem key={type} value={type}>
                {type}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">Status</span>
        <Select
          value={filters.status ?? ''}
          onValueChange={(next: string | null) =>
            onChange({ status: next && next !== ALL ? next : undefined })
          }
        >
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Any status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Any status</SelectItem>
            {STATUSES.map((status) => (
              <SelectItem key={status} value={status}>
                {status}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">Line source</span>
        {/* Finds the spend still standing on its postings — the vouchers whose
            document has not been read, and whose descriptions are therefore the
            bookkeeper's rather than what was bought. */}
        <Select
          value={filters.origin ?? ''}
          onValueChange={(next: string | null) =>
            onChange({ origin: next && next !== ALL ? (next as LineOrigin) : undefined })
          }
        >
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Any source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Any source</SelectItem>
            {LINE_ORIGINS.map((value) => (
              <SelectItem key={value} value={value}>
                {ORIGIN_LABELS[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">Supplier</span>
        {/* A combobox, not a select: a real org has more suppliers than a
            dropdown can hold, and the API already searches them server-side. */}
        <Combobox
          items={vendors}
          value={selectedVendor}
          itemToStringLabel={(vendor: VendorRead) => vendor.name}
          isItemEqualToValue={(a: VendorRead, b: VendorRead) => a.id === b.id}
          onValueChange={(next: VendorRead | null) => onChange({ vendor_id: next?.id })}
          onInputValueChange={onVendorSearch}
        >
          <ComboboxInput placeholder="All suppliers" className="w-52" />
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
