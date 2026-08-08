# frontend-ui-library Specification

## Purpose
TBD - created by syncing change frontend-ui-library. Update Purpose after archive.
## Requirements
### Requirement: Token-driven theming from the ERPSAA theme

The UI library SHALL define a single design-token layer (Tailwind v4 `@theme`
CSS variables) reproducing the ERPSAA theme — canvas `#E9ECEA`, white surfaces,
ink `#091315`, lime accent `#D7FF53`, muted grays, pill/rounded radii, Outfit
display + Inter body — and every component SHALL derive its colors, typography,
radius, and spacing from those tokens rather than hard-coded values.

#### Scenario: Components consume tokens

- **WHEN** a component renders
- **THEN** its colors/radii/fonts come from theme tokens, so changing a token in
  one place restyles the component

#### Scenario: Theme reflects the source

- **WHEN** the library is rendered
- **THEN** the accent, canvas, ink, fonts, and pill/rounded shapes match the
  ERPSAA theme

### Requirement: Accessible primitives built on Base UI

Interactive components SHALL be built on Base UI primitives and SHALL preserve
their accessibility (keyboard interaction, focus management, ARIA, labelled form
fields) and a visible focus indicator.

#### Scenario: Dialog is keyboard-accessible

- **WHEN** a user opens a Dialog and presses Escape
- **THEN** the dialog closes and focus returns to the trigger

#### Scenario: Form controls are labelled

- **WHEN** an input is rendered via the Field wrapper with a label
- **THEN** the label is programmatically associated with the control

### Requirement: Reusable, variant-driven component API

Each component SHALL be a reusable React component that forwards refs, spreads
arbitrary props, and exposes typed `variant`/`size` options where applicable via
a single class-merge utility, so it composes without re-styling.

#### Scenario: Button variants

- **WHEN** `Button` is rendered with `variant="primary"` vs `variant="outline"`
- **THEN** each yields the correct token-based styles from one component

#### Scenario: Class overrides merge

- **WHEN** a caller passes `className` to a component
- **THEN** it merges with (and can override) the component's own classes without
  duplication conflicts

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

### Requirement: Light and dark theming

The library SHALL support light (default) and dark themes via a token set toggled
by a `.dark` class on the document root, with a provider that persists the choice.
The persisted choice SHALL be a *preference* of light, dark, or **system**; when
it is `system` the provider SHALL resolve the applied theme from the operating
system's colour-scheme setting and SHALL follow that setting while it remains
`system`. Consumers SHALL be able to read both the resolved theme and the stored
preference, so a control can show what the user actually chose rather than what
is currently displayed.

#### Scenario: Dark mode swaps tokens

- **WHEN** the dark theme is active
- **THEN** canvas/surface/ink tokens invert while the accent stays consistent

#### Scenario: System preference follows the OS

- **WHEN** the stored preference is `system`
- **THEN** the applied theme matches the operating system's colour scheme, and it
  changes with the OS setting without a reload

#### Scenario: Preference survives a reload

- **WHEN** the user picks a preference and reloads
- **THEN** the same preference is in effect, and a `system` preference is not
  flattened into the light or dark value it happened to resolve to

### Requirement: Kitchen-sink verification route

The app SHALL expose a `/ui` route rendering every component and its variants, so
the theme and component states can be verified visually.

#### Scenario: All components on one page

- **WHEN** `/ui` is opened
- **THEN** each component in the library is rendered with its key variants/states

