import { Outlet, createFileRoute } from '@tanstack/react-router'

/** Layout for the Companies section. */
export const Route = createFileRoute('/_authed/settings/companies')({
  component: Outlet,
  staticData: { title: 'Companies' },
})
