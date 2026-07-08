## Context

`frontend/` is a scaffolded Vite + React 19 app (TanStack Router/Start, Tailwind
v4 via `@tailwindcss/vite`, lucide-react, Bun, Vitest). `frontend/src/styles.css`
currently just `@import "tailwindcss"`. There are no components. Base UI
(base-ui.com) provides unstyled, accessible primitives; the ERPSAA look must come
entirely from tokens + Tailwind classes we author. Tokens below were extracted
from the live theme (`erpsaas.framer.website`) via a headless browser; a viewport
reference is saved at `theme-reference.jpeg` in this change.

## Goals / Non-Goals

**Goals:**
- One token layer (Tailwind v4 `@theme`) that reproduces the ERPSAA theme; every
  component consumes tokens, never hard-coded colors.
- Base UI primitives wrapped as reusable, variant-driven components in
  `frontend/src/components/ui/`, accessible by default.
- A comprehensive first set (primitives + composites + AppShell) sufficient to
  build real admin pages next.

**Non-Goals:**
- Product pages, API wiring, data fetching, auth (later changes).
- A published/versioned package — this is an in-app `ui/` folder, not an npm lib.
- Pixel-cloning marketing sections; we translate the theme into app UI.

## Decisions

### Extracted theme tokens (source of truth)
From the live theme's computed styles:

- **Canvas / background:** `#E9ECEA` (warm sage-gray)
- **Surface / card:** `#FFFFFF`; **muted surface:** `#F3F5F4`
- **Ink / foreground:** `#091315` (near-black, slight teal)
- **Muted foreground:** `#6B6B6B`; **subtle:** `#787E7E`
- **Primary / accent:** `#D7FF53` (lime-chartreuse); **primary-foreground:** `#091315`
- **Inverted surface** (dark sections): `#091315` with `#FFFFFF` text
- **Border / divider:** `rgba(9,19,21,0.08)` (~`#E2E5E3`)
- **Focus ring:** `#091315` at low alpha (accent is too light for a11y contrast)
- **Status (not in theme; harmonized):** success `#3E9B4F`, warning `#E8A13A`,
  danger `#E5484D`, info `#2F6FEB`
- **Radius:** buttons pill (`9999px`); cards `16–24px`. Scale: `sm 8 / md 12 /
  lg 16 / xl 20 / 2xl 24 / full 9999`.
- **Typography:** display/headings **Outfit** 500 (tight tracking at large sizes);
  body **Inter**. Self-hosted via `@fontsource-variable`.
- **Elevation:** flat; soft card shadow `0 1px 2px rgba(9,19,21,.04), 0 8px 24px
  rgba(9,19,21,.05)`.

These live in `frontend/src/styles.css` under `@theme { --color-… ; --font-… ;
--radius-… }`, exposed as Tailwind utilities (`bg-primary`, `text-foreground`,
`rounded-card`, `font-display`). Swapping the theme later = editing this block.

### Base UI + Tailwind, wrapped per component
Each component imports the Base UI primitive and renders it with token classes.
Variants via `class-variance-authority`; class merging via `cn()` = `twMerge(clsx(…))`.
Components forward refs and spread `...props` so they stay reusable and composable.
Example shape: `ui/button.tsx` exports `Button` with `variant` (primary | secondary
| ghost | outline | destructive) and `size` (sm | md | lg | icon), primary = lime
pill with ink text.

### Dark theme
Token set duplicated under a `.dark` selector (canvas → `#091315`, surface →
`#12201F`-ish, ink → `#F3F5F4`, accent unchanged). Toggle by adding `.dark` on
`<html>`; a tiny `ThemeProvider` persists preference. Light is default (matches
the theme).

### File layout
```
frontend/src/components/ui/
  index.ts                 barrel export
  cn.ts                    class-merge util
  button.tsx input.tsx select.tsx checkbox.tsx radio.tsx switch.tsx textarea.tsx
  field.tsx                Label/Field/Error wrappers (Base UI Field)
  dialog.tsx alert-dialog.tsx dropdown-menu.tsx popover.tsx tooltip.tsx tabs.tsx
  toast.tsx                Base UI Toast + provider + useToast
  card.tsx badge.tsx avatar.tsx separator.tsx skeleton.tsx progress.tsx
  table.tsx pagination.tsx data-table.tsx   (data-table on @tanstack/react-table)
  layout/app-shell.tsx sidebar.tsx topbar.tsx
  theme-provider.tsx
```
A `/ui` route renders a kitchen-sink of all components for visual QA.

### Accessibility & testing
Base UI handles focus/keyboard/ARIA; we preserve it (labels wired via `Field`,
`aria-*` passthrough, visible focus ring). Vitest + Testing Library cover
representative behavior (Button variants render; Dialog open/close via trigger;
DataTable sorts + paginates; Toast shows/dismisses).

## Risks / Trade-offs

- **Theme fidelity vs. app usability** — the marketing site is airy with full-pill
  buttons; for dense admin tables we keep pills on buttons but use tighter radii
  on inputs/cells. Documented so it reads as intentional, not drift.
- **Accent contrast** — lime `#D7FF53` fails AA for text; used only as a fill with
  ink text and for non-text highlights; focus/links use ink, not accent.
- **Base UI API surface** — component set is broad; we scope to the listed set and
  add more (Command, Calendar, etc.) in later changes rather than boil the ocean.
- **Font licensing** — Outfit + Inter are OFL (self-host fine). Satoshi (seen on
  the site) is Fontshare-licensed and **omitted**; Outfit covers display needs.
- **Kitchen-sink drift** — the `/ui` route must include every component so visual
  regressions surface; enforced as a task, not automation.
