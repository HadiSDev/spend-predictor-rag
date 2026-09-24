## ADDED Requirements

### Requirement: Searchable Combobox primitive

The library SHALL provide a generic, reusable `Combobox` built on Base UI's
headless combobox and styled with the theme tokens, usable for any list of
options (organizations, vendors, companies, categories) without modification.

It SHALL be generic over the item type, accepting the items, a way to derive each
item's value and label, and an optional item renderer. It SHALL support both
controlled (`value` + `onValueChange`) and uncontrolled (`defaultValue`) use,
a placeholder, a disabled state, and a `render`-able trigger so callers can
present it as a form control, a toolbar filter, or a workspace switcher without
forking the component.

Filtering SHALL be case-insensitive substring matching on the item label by
default and SHALL be overridable by the caller. The component SHALL expose an
empty state for "no matches", a loading state for asynchronously loaded items,
and optional grouping with group labels.

#### Scenario: Type-to-filter narrows the options

- **WHEN** the combobox is open and the user types text matching some option labels
- **THEN** only the matching options remain listed, matching case-insensitively on
  any part of the label

#### Scenario: Selection reports the chosen item

- **WHEN** the user activates an option
- **THEN** the popup closes, the trigger displays that option's label, and
  `onValueChange` fires once with the selected item's value

#### Scenario: Keyboard navigation and dismissal

- **WHEN** the combobox is focused and the user navigates with the arrow keys and
  confirms with Enter
- **THEN** the highlighted option is selected; pressing Escape closes the popup
  without changing the value

#### Scenario: No matches

- **WHEN** the typed query matches no option
- **THEN** the popup shows the empty-state message instead of an empty list

#### Scenario: Loading options

- **WHEN** the combobox is marked as loading
- **THEN** it shows a loading indication in place of the option list rather than
  an empty or "no matches" state

#### Scenario: Accessible by label

- **WHEN** the combobox is rendered inside a `Field` with a label
- **THEN** the input is programmatically associated with that label and exposes
  combobox semantics to assistive technology

## MODIFIED Requirements

### Requirement: Comprehensive component set exported from ui/

The library SHALL provide, and export from `apps/web/src/components/ui/`, at least: Button,
IconButton, Input, NumberInput (`react-number-format`), Textarea, Select, Combobox,
Checkbox, Radio, Switch, Field/Label/Error, Form (`react-hook-form`), Calendar +
DatePicker (`react-day-picker`), Dialog, AlertDialog, DropdownMenu, Tabs, Tooltip, Popover,
Toast, Avatar, Badge, Card (incl. a stat card), Separator, Skeleton, Progress,
Pagination, Table, a sortable+paginated DataTable (`@tanstack/react-table`), and a
reusable AppShell (sidebar + topbar).

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
