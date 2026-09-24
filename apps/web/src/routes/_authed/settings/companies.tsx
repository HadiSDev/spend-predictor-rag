import { Outlet, createFileRoute } from '@tanstack/react-router'

/**
 * Layout for the Companies section. It renders only an `Outlet`: the list lives
 * in `companies.index.tsx` and per-company pages nest under it. Without this,
 * a child route matches — the topbar title even updates — while the parent's
 * own content stays on screen and the child never renders.
 */
export const Route = createFileRoute('/_authed/settings/companies')({
  component: Outlet,
  staticData: { title: 'Companies' },
})
