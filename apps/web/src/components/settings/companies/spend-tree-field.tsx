import * as React from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '#/components/ui'
import type { SpendTreeRead } from '#/lib/api/types'

/** Picker for the company's spend tree, chosen from the organization's trees. */
export function SpendTreeField({
  value,
  trees,
  onChange,
}: {
  value: string
  trees: Array<SpendTreeRead>
  onChange: (next: string) => void
}) {
  const items = React.useMemo(
    () => [
      ...(trees.some((tree) => tree.source === 'default_template')
        ? []
        : [{ value: '', label: 'Default spend tree (will be created)' }]),
      ...trees.map((tree) => ({
        value: tree.id,
        label: `${tree.name} (${tree.max_depth} levels)`,
      })),
    ],
    [trees],
  )
  return (
    <Select
      items={items}
      value={value}
      onValueChange={(next) => onChange(String(next))}
    >
      <SelectTrigger aria-label="Spend tree">
        <SelectValue items={items} />
      </SelectTrigger>
      <SelectContent>
        {items.map((item) => (
          <SelectItem key={item.value || 'default'} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
