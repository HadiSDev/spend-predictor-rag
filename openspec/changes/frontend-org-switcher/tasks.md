## 1. Combobox primitive

- [x] 1.1 Create `apps/web/src/components/ui/combobox.tsx` wrapping Base UI's `Combobox` parts: `Combobox` (Root), `ComboboxInput`, `ComboboxTrigger`, `ComboboxValue`, `ComboboxIcon`, `ComboboxClear`
- [x] 1.2 Add `ComboboxContent` composing Portal + Positioner + Popup + List with the popover token styling used by `SelectContent` (`max-h-72`, `min-w-[var(--anchor-width)]`, `shadow-popover`)
- [x] 1.3 Add `ComboboxItem` (with `ItemIndicator` check), `ComboboxGroup`, `ComboboxGroupLabel`, `ComboboxSeparator` styled to match the Select equivalents
- [x] 1.4 Add `ComboboxEmpty` (no-matches message) and a loading state rendered in place of the list when the caller marks items as loading
- [x] 1.5 Keep the generic `Value` type parameter flowing through Root so object items work via `itemToStringLabel` / `isItemEqualToValue`; keep Base UI's `filter` / `filteredItems` props passthrough for caller-owned filtering
- [x] 1.6 Ensure every part forwards refs, merges a caller `className` via `cn`, and accepts Base UI's `render` prop (trigger especially)
- [x] 1.7 Export the Combobox parts from `apps/web/src/components/ui/index.ts`

## 2. Combobox verification

- [x] 2.1 Add Combobox tests to `apps/web/src/components/ui/ui.test.tsx`: typing filters options case-insensitively; selecting an option closes the popup, updates the trigger text, and fires `onValueChange` once
- [x] 2.2 Add tests for keyboard navigation (arrows + Enter selects, Escape closes without changing value), the empty state, and the loading state
- [x] 2.3 Add a test that a Combobox inside a `Field` is reachable via its label (`getByLabelText`) and exposes combobox role semantics
- [x] 2.4 Add a Combobox section to the `/ui` kitchen-sink route (`apps/web/src/routes/ui.tsx`) showing default, grouped, disabled, empty, and loading states

## 3. Organization switching state

- [x] 3.1 In `apps/web/src/lib/auth.tsx`, add an effect in `AuthProvider` that observes `useAuth().orgId` and, when it changes from a previously seen value, calls `queryClient.clear()`
- [x] 3.2 Remount the authenticated subtree on organization change by keying it on `orgId`, so in-flight requests made with the previous token cannot repopulate mounted observers
- [x] 3.3 Confirm `GET /users/me` refetches after the reset so the principal's `organizationId` and `role` match the new organization
- [x] 3.4 Review `apps/web/src/routes/_authed.tsx` so the pending-org activation and the switcher read memberships through the same `useOrganizationList` options (no second, differently-configured listing)

## 4. Org switcher component

- [x] 4.1 Create `apps/web/src/components/org-switcher.tsx` reading memberships from `useOrganizationList({ userMemberships: { pageSize: 50 } })` and the active org from `useAuth`/`useOrganization`
- [x] 4.2 Render the multi-membership case as a Combobox listing the user's organizations, filtering by name, marking the active one as selected
- [x] 4.3 Render the 0–1 membership case as a static, non-interactive organization label
- [x] 4.4 Render a loading placeholder while the membership list is unresolved
- [x] 4.5 On selection call `setActive({ organization: id })`, then navigate to the dashboard root; on rejection keep the current organization and surface a toast error

## 5. Shell wiring

- [x] 5.1 Place `OrgSwitcher` in the sidebar header of the app shell in `apps/web/src/routes/_authed/index.tsx`, beside the product mark
- [ ] 5.2 Check the switcher's layout at the sidebar width (truncation of long org names, trigger focus ring, popup anchoring) in light and dark themes

## 6. Switcher verification

- [x] 6.1 Test that picking a different organization calls `setActive` with that organization's id (Clerk hooks mocked)
- [x] 6.2 Test the single-membership static label and the loading placeholder
- [x] 6.3 Test that typing filters the membership list
- [x] 6.4 Test the failure path: `setActive` rejects → active organization unchanged, error surfaced, cache not cleared
- [x] 6.5 Test that an `orgId` change clears cached tenant data and reloads the principal

## 7. Wrap-up

- [x] 7.1 Run `pnpm test`, `pnpm lint`, and `pnpm build` in `apps/web/` and fix fallout
- [ ] 7.2 Verify manually against a Clerk user with two organization memberships: switch, confirm dashboard figures and principal role change, confirm no previous-tenant data flashes
