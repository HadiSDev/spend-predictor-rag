## MODIFIED Requirements

### Requirement: Comprehensive component set exported from ui/

The library SHALL provide, and export from `apps/web/src/components/ui/`, at least: Button,
IconButton, Input, NumberInput (`react-number-format`), CurrencyInput, Textarea, Select,
Checkbox, Radio, Switch, Field/Label/Error, Form (`react-hook-form`), Calendar +
DatePicker (`react-day-picker`), Dialog, AlertDialog, Drawer, DropdownMenu, Tabs, Tooltip, Popover,
Toast, Avatar, Badge, Card (incl. a stat card), Separator, Skeleton, Progress,
Pagination, Table, a sortable+paginated DataTable (`@tanstack/react-table`), and a
reusable AppShell (sidebar + topbar).

The Drawer SHALL be a side-anchored panel built on the same Base UI dialog
primitive as Dialog, so it inherits focus trapping, escape dismissal, and scroll
locking, and SHALL support anchoring to either side.

**These components SHALL be the mandated controls for their data types, not
optional alternatives to a bare text input.** A numeric value SHALL be entered
through `NumberInput` or `CurrencyInput`, and a date through `DatePicker`.
Providing a control the product does not use is indistinguishable from not having
built it: the library shipped both of these and every real editing surface went
on using text boxes, with the silent `NaN`-to-null data loss that implies.

#### Scenario: Single import surface

- **WHEN** a page imports from `apps/web/src/components/ui`
- **THEN** every listed component is available from the barrel export

#### Scenario: DataTable sorts and paginates

- **WHEN** a column header is activated and a page is changed on the DataTable
- **THEN** the rows reorder by that column and the visible page updates

#### Scenario: Form surfaces react-hook-form validation

- **WHEN** a `Form` field with a required rule is submitted empty and then filled
- **THEN** the field's error message renders (label associated, control marked
  `aria-invalid`) and, once valid, the error clears and submission proceeds

#### Scenario: Drawer opens from a side and dismisses

- **WHEN** a Drawer is opened
- **THEN** it enters from its anchored side with focus moved inside it, and
  escape or its close control dismisses it and returns focus to the trigger

#### Scenario: No editing surface enters a number as free text

- **WHEN** the application's editing surfaces are inspected
- **THEN** no monetary or quantity field is a bare text input, and no date field
  is a bare text input

