## Why

The `frontend/` app is scaffolded (Vite + React 19 + TanStack Router + Tailwind
v4 + Bun) but has no components. Before building any page we need a reusable UI
component library that encodes the **ERPSAA Framer theme**
(erpsaas.framer.website) as design tokens, so every page inherits the same look
and pages become composition, not re-styling. Components are built on **Base UI**
(headless, accessible primitives) and styled with Tailwind v4 tokens extracted
from the theme.

## What Changes

- **Design tokens** — encode the theme (extracted from the live site) as Tailwind
  v4 `@theme` CSS variables: warm-gray canvas `#E9ECEA`, white surfaces, near-black
  ink `#091315`, lime accent `#D7FF53`, muted grays, pill/rounded radii, flat/soft
  shadows; **Outfit** (display) + **Inter** (body) fonts self-hosted. Light theme
  primary with a dark-theme token set.
- **Primitive layer on Base UI** — install `@base-ui-components/react`; wrap each
  primitive as a styled, variant-driven, reusable component in `frontend/src/components/ui/`.
- **Component set (comprehensive):** Button, IconButton, Input, Textarea, Select,
  Checkbox, Radio, Switch, Field/Label/Error (form wrappers), Dialog, AlertDialog,
  DropdownMenu, Tabs, Tooltip, Popover, Toast, Avatar, Badge, Card (+ stat card),
  Separator, Skeleton, Progress, Pagination, Table, and a composite **DataTable**
  (sortable + paginated). Plus a reusable **AppShell** (sidebar + topbar) matching
  the theme's dashboard.
- **Reusability plumbing** — `cn()` (clsx + tailwind-merge), `class-variance-authority`
  for variants, a barrel export `frontend/src/components/ui/index.ts`, and lucide-react icons.
- **Kitchen-sink route** (`/ui`) rendering every component/variant to verify the
  theme visually and catch regressions.
- Light unit tests (Vitest + Testing Library) for representative components.

## Capabilities

### New Capabilities
- `frontend-ui-library`: a token-driven, Base UI–based, reusable React component
  library in `frontend/src/components/ui/` that renders the ERPSAA theme and is the single
  source of UI primitives for all pages.

### Modified Capabilities

## Impact

- `frontend/` only (no backend/API change): new `frontend/src/components/ui/**`, tokens in
  `frontend/src/styles.css` (`@theme`), fonts, a `/ui` route, and new deps
  (`@base-ui-components/react`, `@tanstack/react-table` (DataTable),
  `react-number-format` (NumberInput), `react-day-picker` (DatePicker),
  `react-hook-form` (Form), `class-variance-authority`, `clsx`, `tailwind-merge`,
  `@fontsource-variable/{inter,outfit}`).
- **Non-goals:** building actual product pages/screens, wiring to the web API,
  data fetching, and auth — those come after the library exists.
- Theme reference captured at `openspec/changes/frontend-ui-library/theme-reference.jpeg`.
