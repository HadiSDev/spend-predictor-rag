## ADDED Requirements

### Requirement: A reusable CurrencyInput

The library SHALL provide and export a `CurrencyInput` — a money field bound to
an ISO 4217 currency code — so that every place a customer types an amount does
so identically.

- It SHALL take a currency code and render the amount in that currency's
  conventions, defaulting to 2 decimal places.
- It SHALL emit the **unformatted** numeric value, never the display string, so a
  caller never parses back out what the component just formatted.
- It SHALL emit `null` for an empty field and SHALL NEVER emit `NaN`. A figure
  that cannot be parsed is no figure, not a broken one.
- It SHALL right-align its value and use tabular figures, so a column of amounts
  is scannable.
- With no currency code it SHALL still render as a plain 2-decimal number rather
  than failing — a line whose invoice states no currency is an ordinary case.

#### Scenario: An amount is formatted for its currency

- **WHEN** `CurrencyInput` is rendered with currency `DKK` and value `5400`
- **THEN** the displayed value carries the thousands separator and two decimals

#### Scenario: The caller receives a number, not a string

- **WHEN** the user types an amount
- **THEN** the change handler receives the unformatted numeric value

#### Scenario: An empty field is null, not NaN

- **WHEN** the user clears the field
- **THEN** the change handler receives `null`

#### Scenario: A missing currency still renders

- **WHEN** `CurrencyInput` is rendered with no currency code
- **THEN** it renders a 2-decimal number field rather than erroring

## MODIFIED Requirements

### Requirement: Comprehensive component set exported from ui/

The library SHALL provide, and export from `frontend/src/components/ui/`, at least: Button,
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

- **WHEN** a page imports from `frontend/src/components/ui`
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
