## MODIFIED Requirements

### Requirement: Comprehensive component set exported from ui/

The library SHALL provide, and export from `frontend/src/components/ui/`, at least: Button,
IconButton, Input, NumberInput (`react-number-format`), Textarea, Select,
Checkbox, Radio, Switch, Field/Label/Error, Form (`react-hook-form`), Calendar +
DatePicker (`react-day-picker`), Dialog, AlertDialog, Drawer, DropdownMenu, Tabs, Tooltip, Popover,
Toast, Avatar, Badge, Card (incl. a stat card), Separator, Skeleton, Progress,
Pagination, Table, a sortable+paginated DataTable (`@tanstack/react-table`), and a
reusable AppShell (sidebar + topbar).

The Drawer SHALL be a side-anchored panel built on the same Base UI dialog
primitive as Dialog, so it inherits focus trapping, escape dismissal, and scroll
locking, and SHALL support anchoring to either side.

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
