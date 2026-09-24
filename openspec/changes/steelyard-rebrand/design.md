## Context

`design/` (untracked) holds the Steelyard logo pack. It has SVG, PNG, favicon
and social variants, plus a README of usage rules: black `#0A0A0A` and white
only, the wordmark as Geist SemiBold outlines, a 80 px lockup / 20 px symbol
minimum, a thicker-arm favicon variant below 32 px, and a ban on recolouring,
effects, tilting, stretching or retyping. The social images carry the tagline
*"Know the true price of everything you buy."*

The frontend's theme is almost entirely token-driven. `apps/web/src/styles.css`
defines semantic CSS variables in `:root`/`.dark`, and `@theme inline` maps them
to Tailwind utilities. That makes the palette swap small and mostly
centralised. The surveyed exceptions:

- **The logo is composed, not drawn**, in four places: `app-shell.tsx`,
  `sign-in.tsx`, `ui/loading-screen.tsx` and the `/ui` showcase
  (`routes/ui.tsx`). Each is a `bg-primary` tile with a Lucide icon next to the
  text "Spend Predictor".
- **Lime was used as a tint**, not only as a fill. Examples are the active nav
  (`bg-primary/15`), the connector picker's selection (`bg-primary/5` plus a
  primary ring), the loading glow (`bg-primary/25 blur`) and the date picker's
  selected day. A tint of lime reads as a highlight; a tint of near-black reads
  as dirty grey.
- **`hover:brightness-95`** on the primary button is invisible on near-black.
- Hard-coded hex appears only in third-party ERP artwork
  (`assets/erp/*.svg`), which is exempt.
- There is no chart library; the dashboard figures use tokens.

Fonts come from `@fontsource-variable/inter` and `/outfit`. Geist is not
installed, and by project rule agents never run package installs here.

Infra: the PostgreSQL database, role and password are all `spend_predictor`
in `docker-compose.yml`, in the default `DATABASE_URL` in
`web_api/config.py` and `db/session.py`, and in `.env.example`. The compose
project name is derived from the folder (`spend-predictor-rag`). Data lives in a
bind-mounted `./pgdata`, where `POSTGRES_*` variables only apply at first
initialisation.

## Goals / Non-Goals

**Goals:**
- One product name, Steelyard, on every surface a person reads.
- A monochrome UI that still has clear hierarchy. The memory note "UI needs
  visual weight" says pale, flat controls get rejected, so contrast has to do
  the work the accent did.
- The logo used exactly as the pack's rules allow: drawn from outlines, in ink,
  above the minimum sizes.
- Local infra renamed without anyone losing their dev database.

**Non-Goals:**
- A landing or marketing page. The tagline is used only in share metadata.
- Renaming the repository folder or the GitHub repository. That would also move
  the Claude project memory directory, so it is an owner decision, listed as a
  follow-up.
- Renaming workspace packages (`web-api`, `ai-api`, `mock-erp`) or
  `ai_api.procurement_agent`. They describe function, not brand.
- Clerk's hosted pages or email branding, which live in Clerk's dashboard.
- Redesigning layouts or information architecture. This change covers the
  palette, type, logo and name, not page structure.

## Decisions

**1. `brand/` is the source, `public/` holds copies.** `git mv` is impossible
because `design/` is untracked, so the files are `mv`'d to `brand/` and added.
`brand/` keeps the pack's inner structure flattened by one level
(`brand/svg`, `brand/png`, `brand/favicon`, `brand/social`, `brand/README.md`).
The two loose PNGs at `design/`'s root duplicate pack files and are dropped
after a byte comparison. `apps/web/public` receives exact copies of
`favicon.ico`, `favicon.svg`, `apple-touch-icon.png`, `favicon-192.png`,
`favicon-512.png` and `og-image-1200x630.png`. The Vite starter's `logo192.png`
and `logo512.png` are deleted. A small test asserts byte equality between each
public copy and its `brand/` source, so a re-export cannot drift silently.
- *Alternative: have Vite import from `../../brand` at build time.* Rejected:
  favicons and the manifest must be served at stable root URLs, and `public/`
  is where TanStack Start serves them from.

**2. One `Logo` component, drawn from the pack's geometry.** It lives in
`components/brand/logo.tsx` and takes `variant: 'lockup' | 'symbol'` and a
size. The symbol is three primitives (two circles and a bar), copied from
`steelyard-symbol-black.svg`. The favicon variant (thicker arm, used below
32 px) is copied from `favicon.svg`. The lockup inlines the wordmark's outlined
`<path>` from `steelyard-lockup-black.svg` verbatim. Every fill is
`currentColor` and the component sets `text-foreground`. Because
`--foreground` is exactly `#0A0A0A` in light mode and `#FFFFFF` in dark mode,
"black on light, white on dark" holds by construction. The component has
`role="img"` and `aria-label="Steelyard"`, and it clamps its rendered size to
the minimums.
- *Alternative: `<img src="/…svg">`.* Rejected: it can't follow the theme
  without swapping files, and it needs two requests per render site.
- *Alternative: set "Steelyard" in Geist SemiBold text.* Rejected by the pack's
  rules ("don't retype the wordmark"). Outlines also look the same whether or
  not Geist has loaded.

**3. The monochrome token set.** Light mode:

| token | value | note |
|---|---|---|
| `--foreground`, `--primary`, `--inverted` | `#0A0A0A` | the ink; primary action = ink |
| `--primary-foreground`, `--inverted-foreground` | `#FFFFFF` | |
| `--card`, `--popover`, `--secondary` | `#FFFFFF` | |
| `--canvas` | `#F5F5F5` | neutral, so white cards separate from it |
| `--muted` | `#F0F0F0` | |
| `--muted-foreground` | `#5C5C5C` | ≥ 4.5:1 on white and on canvas |
| `--subtle-foreground` | `#737373` | ≥ 4.5:1 on white |
| `--accent` / `--accent-foreground` | `#0A0A0A` / `#FFFFFF` | kept as aliases of the ink so existing `accent` utilities stay valid |
| `--border` / `--input` | `rgb(10 10 10 / 0.10)` / `rgb(10 10 10 / 0.18)` | |
| `--ring` | `rgb(10 10 10 / 0.55)` | focus must stay visible without a hue |

Dark mode inverts it: canvas `#0A0A0A`, card and popover `#141414`, muted
`#1C1C1C`, foreground and primary `#FFFFFF`, primary-foreground `#0A0A0A`,
white-alpha borders, and a white ring. Status tokens keep their current hues.
The implementer checks that each keeps ≥ 4.5:1 for its foreground pair on both
canvases. Exact greys may be tuned during apply against the contrast checks,
but no hue may enter.
- *Alternative: keep one accent for data highlights.* Rejected: the pack says
  "never use any other colour", and the user chose monochrome.

**4. Tints become structure.** Each place that tinted lime gets an explicit
monochrome treatment rather than a fainter version of the same idea:
- Active sidebar item: a solid `bg-primary text-primary-foreground` pill, i.e.
  inverted ink. This is the anchor the memory note asks for.
- Choice cards (the connector picker): selected gets a `border-foreground`, a
  `ring-1 ring-foreground` and a heavier title weight. Unselected keeps the
  neutral border.
- Date picker selected day: an ink fill with white text (the variables in
  `styles.css`).
- Loading screen: the blurred glow is removed. An ink glow is a smudge, and the
  brand forbids effects on the mark. The animated bars stay, drawn in ink.
- Primary button hover: `hover:bg-primary/90` instead of `brightness-95`, which
  gives a visible lift in both modes.
- The `bg-primary` icon tile next to stat cards (`card.tsx`) becomes an inverted
  ink tile. That is still a strong anchor, and it works because it is a fill,
  not a tint.

**5. Geist through Fontsource, like the fonts it replaces.**
`@fontsource-variable/geist` and `@fontsource-variable/geist-mono` replace
`inter` and `outfit`. `--font-sans` and `--font-display` both become
`'Geist Variable'`, and `--font-mono` becomes `'Geist Mono Variable'`. Headings
keep the `font-display` utility, so no component changes for that. Amounts that
already use `tabular-nums` get `font-mono` only where columns must align (table
money cells). **The developer runs the install**; the apply stops at that task
until it is done.
- *Alternative: the `geist` npm package (Vercel's).* Rejected: it is built
  around `next/font`, and the Fontsource packages match how this app already
  loads fonts.

**6. The head carries the brand metadata.** `__root.tsx` `head()` sets the
title "Steelyard", the three icon links from the pack README, `theme-color`
`#0A0A0A`, and `og:*` / `twitter:*` tags with the tagline as description. The
OG image URL is relative (`/og-image-1200x630.png`), because there is no
production origin yet. An absolute origin is a follow-up once one exists.
`manifest.json` gets name, short_name, the 192/512 icons and the theme colour.

**7. The database is renamed in place, not re-created.**
`scripts/rename-dev-db.sh` (repo root, dev-only) runs `psql` through
`docker compose exec postgres`, or through `--container NAME`. *Revised during
apply:* the first draft created `steelyard`, reassigned ownership and dropped
`spend_predictor`. But `POSTGRES_USER` is the cluster's **bootstrap
superuser**: it owns `postgres` and the template databases and cannot be
dropped. So the role is **renamed** instead. A session cannot rename its own
role, so the steps are:
1. as `spend_predictor`, create a temporary superuser `steelyard_rename_tmp`;
2. as that user, run `ALTER ROLE spend_predictor RENAME TO steelyard`, reset
   its password (a rename clears an MD5 hash), and
   `ALTER DATABASE spend_predictor RENAME TO steelyard`;
3. as `steelyard`, drop the temporary role.

It refuses while sessions are open on the database, rather than terminating
them. OIDs, ownership and grants are untouched, so the result is the same
cluster a fresh `steelyard` init would produce. It was tested on a throwaway
`postgres:16`: the data and alembic head survive, the role stays superuser and
owns all databases, TCP password login works, and it refuses with a session
open. Rollback works with `--from steelyard --to spend_predictor`.
The script is idempotent: it exits 0 and says so if `steelyard` already exists
and `spend_predictor` does not. It is safe to run against a fresh stack, where
it is a no-op. `docker-compose.yml` gains `name: steelyard` and the new
`POSTGRES_*` values. The `.env.example` `DATABASE_URL` changes accordingly.
The user's own `.env` is **not** edited by the agent; the tasks tell the user
to change it.
- *Alternative: dump, restore and re-init.* Rejected: slower, and it risks
  losing the dev org's real Billy data.
- *Alternative: keep the old DB name.* Rejected by the user ("Everything").

**8. The brand gets tests of its own.** Nothing asserts the product name today
(checked), so nothing breaks. That is also why a stray "Spend Predictor" could
survive unnoticed. New tests cover four things:
- the app shell, sign-in and loading screen each render the logo by its
  accessible name "Steelyard", with no text node spelling the name, which pins
  "rendered, not retyped";
- `Logo` switches to the favicon geometry below 32 px and clamps to the
  minimums;
- the public assets are byte-equal to `brand/`;
- no legacy name or legacy palette hex (`#d7ff53`, `#e9ecea`, `#091315`) remains
  in `apps/web/src`. This is a source-scan test, so the rule outlives this
  change.

## Risks / Trade-offs

- [Monochrome reads flat and gets rejected, per memory] → Decision 4 is exactly
  the counter: inverted ink for the active item, ink borders and weight for
  selection, ink tiles for stat icons. The apply ends with screenshots of the
  dashboard, entries, settings and sign-in in both themes, for the user to
  judge before merge.
- [Status colours become the only hue, so they shout] → That is their job. They
  are audited to appear only for status, never for decoration (scenario in the
  UI spec).
- [The DB rename breaks every running worktree and agent session whose `.env`
  says `spend_predictor`] → The script refuses to run while connections exist.
  The commit message and CLAUDE.md state the one-line `.env` change. Other
  worktrees under `.claude/worktrees` and `.kilo/worktrees` are listed in the
  tasks for the user to update.
- [Renaming the compose project orphans the old containers and network] → The
  old containers keep running under `spend-predictor-rag`. The tasks include
  `docker compose -p spend-predictor-rag down` (not `-v`; `pgdata` is a bind
  mount, so no data is removed) before `docker compose up`.
- [The Geist install can't be done by the agent] → The apply pauses at that task
  and asks. Everything before it (assets, tokens except the font family, logo,
  names) proceeds.
- [Inline lockup path is ~9 KB in the JS bundle] → Acceptable: it replaces a
  Lucide icon plus text, and it is rendered in four places from one module.

## Migration Plan

1. The frontend and backend rename lands in one commit, with no infra
   dependency.
2. Infra lands in a second commit: compose, config defaults, `.env.example` and
   the script.
3. The developer, once, stops the API and runners, then runs
   `docker compose -p spend-predictor-rag down`, `docker compose up -d
   postgres` and `scripts/rename-dev-db.sh`. They update `DATABASE_URL` in
   `.env` and in each worktree's `.env`, then run
   `uv run alembic -c apps/web-api/alembic.ini current` to confirm.

Rollback: revert the commits. The DB rename reverses with the same script and
the names swapped; the script takes `--from`/`--to` for exactly this.

## Open Questions

- Should the canvas be pure white (`#FFFFFF`) with cards separated by border
  alone, or the proposed `#F5F5F5`? The default is `#F5F5F5`, because
  white-on-white cards lose the elevation the current UI relies on. It is easy
  to flip in one token.
