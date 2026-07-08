## 1. Setup & tokens

- [x] 1.1 Add deps (Bun): `@base-ui-components/react`, `class-variance-authority`,
  `clsx`, `tailwind-merge`, `@fontsource-variable/inter`, `@fontsource-variable/outfit`
- [x] 1.2 Define the token layer in `frontend/src/styles.css` `@theme`: colors
  (canvas/surface/muted/foreground/muted-foreground/border/ring/primary+foreground/
  inverted/status), radii (sm..2xl+full), font families, card shadow; import fonts
- [x] 1.3 Add `.dark` token overrides; add `frontend/src/components/ui/theme-provider.tsx`
  (persisted light/dark toggle) and `frontend/src/components/ui/cn.ts` (twMerge+clsx)

## 2. Form & control primitives

- [x] 2.1 `button.tsx` (variants: primary/secondary/outline/ghost/destructive;
  sizes sm/md/lg/icon; pill) + `icon-button.tsx`
- [x] 2.2 `input.tsx`, `textarea.tsx`, `select.tsx` (Base UI Select)
- [x] 2.2b `number-input.tsx` (`react-number-format`), `calendar.tsx` +
  `date-picker.tsx` (`react-day-picker` in a Popover)
- [x] 2.3 `checkbox.tsx`, `radio.tsx`, `switch.tsx`
- [x] 2.4 `field.tsx` — Base UI Field/Label/Error wrappers wiring labels + errors
- [x] 2.4b `form.tsx` — `react-hook-form` field components (shadcn-style):
  `Form`/`FormField`/`FormItem`/`FormLabel`/`FormControl`/`FormDescription`/
  `FormMessage` + `useFormField()`; renders RHF validation errors, wires aria

## 3. Overlay & navigation primitives

- [x] 3.1 `dialog.tsx`, `alert-dialog.tsx`
- [x] 3.2 `dropdown-menu.tsx`, `popover.tsx`, `tooltip.tsx`
- [x] 3.3 `tabs.tsx`
- [x] 3.4 `toast.tsx` — Base UI Toast provider + `useToast`

## 4. Display & data

- [x] 4.1 `card.tsx` (Card + Header/Content/Footer + StatCard), `badge.tsx`,
  `avatar.tsx`, `separator.tsx`, `skeleton.tsx`, `progress.tsx`
- [x] 4.2 `table.tsx` (styled primitives) + `pagination.tsx`
- [x] 4.3 `data-table.tsx` — composite over the styled Table, powered by
  `@tanstack/react-table` (standard `ColumnDef`s, client sort + pagination)

## 5. Layout

- [x] 5.1 `layout/sidebar.tsx`, `layout/topbar.tsx`, `layout/app-shell.tsx`
  (theme dashboard shell: rounded sidebar nav w/ lucide icons + topbar + content)

## 6. Wiring, showcase, tests

- [x] 6.1 `frontend/src/components/ui/index.ts` barrel export for all components
- [x] 6.2 `/ui` kitchen-sink route rendering every component + variants/states
- [x] 6.3 Vitest + Testing Library: Button variants; Dialog open/close (Esc +
  trigger); Field label association; DataTable sort + paginate; Toast show/dismiss
- [x] 6.4 `bun run build` succeeds; `bun run test` green; `/ui` renders (screenshot
  check against `theme-reference.jpeg`)

## 7. Docs

- [x] 7.1 `frontend/README.md`: how the token layer works, how to add a component,
  the `/ui` route; note Base UI + Tailwind v4 conventions
