import { cn } from '#/components/ui'
import type { ErpTypeRead } from '#/lib/api/types'
import { ErpBrandMark } from './erp-brand-mark'

/** The connector picker: one card per registered connector. */
export function ErpTypeGrid({
  erpTypes,
  value,
  onSelect,
}: {
  erpTypes: Array<ErpTypeRead>
  value: string
  onSelect: (erpType: string) => void
}) {
  return (
    <div
      role="radiogroup"
      aria-label="ERP system"
      className="grid gap-2 sm:grid-cols-2"
    >
      {erpTypes.map((type) => (
        <label
          key={type.erp_type}
          className="group cursor-pointer"
          data-testid={`erp-type-${type.erp_type}`}
        >
          <input
            type="radio"
            name="erp-type-choice"
            className="peer sr-only"
            value={type.erp_type}
            checked={value === type.erp_type}
            onChange={() => onSelect(type.erp_type)}
          />
          <span
            className={cn(
              'flex h-full items-start gap-3 rounded-lg border border-input bg-card p-3 transition',
              'group-hover:border-ring group-hover:bg-muted/40',
              'peer-checked:border-foreground peer-checked:ring-1 peer-checked:ring-foreground peer-checked:[&_[data-choice-title]]:font-semibold',
              'peer-focus-visible:ring-2 peer-focus-visible:ring-ring',
            )}
          >
            <ErpBrandMark slug={type.brand_slug} label={type.label} />
            <span className="min-w-0 flex-1">
              <span
                data-choice-title
                className="block truncate text-sm font-medium text-foreground"
              >
                {type.label}
              </span>
              {type.description ? (
                <span className="mt-0.5 block text-sm text-muted-foreground">
                  {type.description}
                </span>
              ) : null}
            </span>
          </span>
        </label>
      ))}
    </div>
  )
}
