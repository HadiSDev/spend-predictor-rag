# Steelyard — admin panel frontend

Vite + React 19 + TanStack Start, styled with Tailwind v4 and a reusable UI
component library built on [Base UI](https://base-ui.com/) primitives.

## Application (auth + dashboard)

The app authenticates against the Clerk-backed web API and renders a live
dashboard.

- **Auth** — Clerk via `@clerk/tanstack-react-start`. `ClerkProvider` is mounted
  in `src/routes/__root.tsx`; `clerkMiddleware()` is registered in `src/start.ts`
  so server-side `auth()` works. The sign-in screen (`src/routes/sign-in.tsx`) is
  a **custom** form built from the UI library, driving Clerk's `useSignIn` future
  API (`signIn.password()` → `signIn.finalize()`, and `signIn.sso()` for the
  optional Google button). OAuth returns to `src/routes/sso-callback.tsx`.
- **Route protection** — `src/routes/_authed.tsx` is a pathless layout whose
  `beforeLoad` runs Clerk `auth()` in a server function and redirects signed-out
  users to `/sign-in`. Authenticated pages nest under it (the dashboard is
  `src/routes/_authed/index.tsx`, served at `/`); future `/admin/*` routes nest
  here too.
- **Principal & roles** — `src/lib/auth/auth.tsx` provides `AuthProvider` (loads
  `GET /users/me`), `usePrincipal()` (`{ …, isSystemAdmin }`), `useApi()`, and a
  `requireSystemAdmin` guard helper for future admin routes.
- **API client & data** — `src/lib/api/api-client.ts` attaches the Clerk session
  token as a Bearer credential to `VITE_API_BASE_URL`; data is fetched with
  TanStack Query (`src/lib/api/reports.ts`, `src/lib/api/users.ts`) through the
  `@tanstack/react-router-ssr-query` integration wired in `src/router.tsx`.
- **Dashboard** — the themed `AppShell` with stat cards + a spend-by-category
  table from `GET /reports/*` (org-wide), with loading / empty / error states.
  Money is always grouped by currency, never summed across currencies. The pure
  content lives in `src/components/dashboard/`.

### Environment

Copy `.env.example` to `.env` and set:

- `VITE_CLERK_PUBLISHABLE_KEY` — Clerk publishable key (same instance the API
  verifies). Required; the app shows a config error without it.
- `VITE_API_BASE_URL` — web API base URL (e.g. `http://localhost:8100`).
- `VITE_CLERK_GOOGLE_OAUTH=true` — optional; shows the Google sign-in button
  (only when the provider is enabled on the Clerk instance).

In dev the web API's `WEB_API_CORS_ORIGINS` must include the frontend origin
(`http://localhost:3100`).

## UI component library (`src/components/ui/`)

`src/components/ui/` is the design system: token-driven, accessible, reusable components
that render the **Steelyard** palette — black `#0A0A0A` and white, with status
colours as the only hue (see `brand/README.md` at the repository root). Import everything from the barrel:

```tsx
import { Button, Card, DataTable, useToast } from '#/components/ui'
```

Browse every component and variant at the **`/ui`** kitchen-sink route
(`src/routes/ui.tsx`) — run `bun run dev` and open http://localhost:3100/ui.

### Design tokens

The theme lives entirely in **design tokens**, not in components. Semantic CSS
variables are defined in `src/styles.css` under `:root` (light) and `.dark`, and
wired into Tailwind utilities via `@theme inline`. To re-theme, edit the token
values in one place — every component follows:

- Colors: `bg-primary` (the ink — the primary action), `text-foreground` (ink),
  `bg-card`, `bg-muted`, `border-border`, `text-muted-foreground`, status colors
  (`success`/`warning`/`destructive`/`info`, the only hue, and only for status).
  There is no accent: an active or selected state is an ink fill or ink border.
- Type: Geist throughout (`font-display` and `font-sans`), Geist Mono
  (`font-mono`) for figures that must align.
- Logo: `<Logo>` from `#/components/brand/logo` — never the product name typed
  beside an icon.
- Shape/elevation: `rounded-card`, `rounded-full` (pill buttons), `shadow-card`.

Fonts are self-hosted via `@fontsource-variable/{geist,geist-mono}`. Dark mode is a
`.dark` class on `<html>`, toggled by the `ThemeProvider` (`useTheme()`).

### Conventions (Base UI + Tailwind v4)

- Each component wraps a Base UI primitive (`@base-ui-components/react/<part>`)
  and styles it with token classes; refs are forwarded and props spread.
- Variants use `class-variance-authority`; `className` merges via `cn()`
  (`clsx` + `tailwind-merge`), so callers can override any class.
- `DataTable` is powered by `@tanstack/react-table` (standard `ColumnDef`s;
  carry `meta: { align, className }` for cell presentation) over the styled
  `Table` primitives.
- `NumberInput` wraps `react-number-format`; `DatePicker` puts a
  `react-day-picker` `Calendar` in a `Popover`. The calendar is themed by
  overriding `--rdp-*` variables on `.rdp-root` in `styles.css`.
- `Form` connects any control to `react-hook-form` (shadcn-style): `Form` is
  RHF's `FormProvider`, `FormField` is a `Controller`, and `FormItem` /
  `FormLabel` / `FormControl` / `FormDescription` / `FormMessage` share a
  context (`useFormField()`) that wires ids + aria and renders the field's
  validation error automatically. `FormControl` clones its single child, so it
  wraps `Input`, `NumberInput`, `Select`, etc. without extra deps.
- App-wide providers (`ThemeProvider`, `TooltipProvider`, `ToastProvider`) are
  mounted once in `src/routes/__root.tsx`.

### Adding a component

1. Create `src/components/ui/<group>/<name>.tsx` in the group it belongs to
   (`actions`, `forms`, `overlays`, `data`, `feedback`, `display`, `layout`). For an interactive control, import the Base UI
   part and style it (see `overlays/dialog.tsx` / `forms/select.tsx` as references); for a
   plain element, use a `forwardRef` + `cva` + `cn()` (see `actions/button.tsx`).
2. Only use token classes — never hard-coded colors.
3. Export it from `src/components/ui/index.ts`.
4. Add it (with its variants/states) to the `/ui` route and a test in
   `src/components/ui/ui.test.tsx`.

# Getting Started

To run this application:

```bash
bun install
bun --bun run dev
```

# Building For Production

To build this application for production:

```bash
bun --bun run build
```

## Testing

This project uses [Vitest](https://vitest.dev/) for testing. You can run the tests with:

```bash
bun --bun run test
```

## Styling

This project uses [Tailwind CSS](https://tailwindcss.com/) for styling.

### Removing Tailwind CSS

If you prefer not to use Tailwind CSS:

1. Remove the demo pages in `src/routes/demo/`
2. Replace the Tailwind import in `src/styles.css` with your own styles
3. Remove `tailwindcss()` from the plugins array in `vite.config.ts`
4. Uninstall the packages: `bun install @tailwindcss/vite tailwindcss -D`

## Linting & Formatting


This project uses [eslint](https://eslint.org/) and [prettier](https://prettier.io/) for linting and formatting. Eslint is configured using [tanstack/eslint-config](https://tanstack.com/config/latest/docs/eslint). The following scripts are available:

```bash
bun --bun run lint
bun --bun run format
bun --bun run check
```


## Deploy with Nitro

This project uses Nitro as a generic server adapter, so it can run on any Node-compatible host.

```bash
npm run build
node dist/server/index.mjs
```

The build output is a self-contained Node server. To deploy, push the `dist/` directory to your host (Render, Fly.io, your own VPS, etc.) and run the server command above.

For host-specific presets (Vercel, Netlify, Cloudflare, AWS Lambda, etc.) and tuning, see https://v3.nitro.build/deploy.



## Routing

This project uses [TanStack Router](https://tanstack.com/router) with file-based routing. Routes are managed as files in `src/routes`.

### Adding A Route

To add a new route to your application just add a new file in the `./src/routes` directory.

TanStack will automatically generate the content of the route file for you.

Now that you have two routes you can use a `Link` component to navigate between them.

### Adding Links

To use SPA (Single Page Application) navigation you will need to import the `Link` component from `@tanstack/react-router`.

```tsx
import { Link } from "@tanstack/react-router";
```

Then anywhere in your JSX you can use it like so:

```tsx
<Link to="/about">About</Link>
```

This will create a link that will navigate to the `/about` route.

More information on the `Link` component can be found in the [Link documentation](https://tanstack.com/router/v1/docs/framework/react/api/router/linkComponent).

### Using A Layout

In the File Based Routing setup the layout is located in `src/routes/__root.tsx`. Anything you add to the root route will appear in all the routes. The route content will appear in the JSX where you render `{children}` in the `shellComponent`.

Here is an example layout that includes a header:

```tsx
import { HeadContent, Scripts, createRootRoute } from '@tanstack/react-router'

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'My App' },
    ],
  }),
  shellComponent: ({ children }) => (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        <header>
          <nav>
            <Link to="/">Home</Link>
            <Link to="/about">About</Link>
          </nav>
        </header>
        {children}
        <Scripts />
      </body>
    </html>
  ),
})
```

More information on layouts can be found in the [Layouts documentation](https://tanstack.com/router/latest/docs/framework/react/guide/routing-concepts#layouts).

## Server Functions

TanStack Start provides server functions that allow you to write server-side code that seamlessly integrates with your client components.

```tsx
import { createServerFn } from '@tanstack/react-start'

const getServerTime = createServerFn({
  method: 'GET',
}).handler(async () => {
  return new Date().toISOString()
})

// Use in a component
function MyComponent() {
  const [time, setTime] = useState('')
  
  useEffect(() => {
    getServerTime().then(setTime)
  }, [])
  
  return <div>Server time: {time}</div>
}
```

## API Routes

You can create API routes by using the `server` property in your route definitions:

```tsx
import { createFileRoute } from '@tanstack/react-router'
import { json } from '@tanstack/react-start'

export const Route = createFileRoute('/api/hello')({
  server: {
    handlers: {
      GET: () => json({ message: 'Hello, World!' }),
    },
  },
})
```

## Data Fetching

There are multiple ways to fetch data in your application. You can use TanStack Query to fetch data from a server. But you can also use the `loader` functionality built into TanStack Router to load the data for a route before it's rendered.

For example:

```tsx
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/people')({
  loader: async () => {
    const response = await fetch('https://swapi.dev/api/people')
    return response.json()
  },
  component: PeopleComponent,
})

function PeopleComponent() {
  const data = Route.useLoaderData()
  return (
    <ul>
      {data.results.map((person) => (
        <li key={person.name}>{person.name}</li>
      ))}
    </ul>
  )
}
```

Loaders simplify your data fetching logic dramatically. Check out more information in the [Loader documentation](https://tanstack.com/router/latest/docs/framework/react/guide/data-loading#loader-parameters).

# Demo files

Files prefixed with `demo` can be safely deleted. They are there to provide a starting point for you to play around with the features you've installed.

# Learn More

You can learn more about all of the offerings from TanStack in the [TanStack documentation](https://tanstack.com).

For TanStack Start specific documentation, visit [TanStack Start](https://tanstack.com/start).
