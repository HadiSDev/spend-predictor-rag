## Why

The product now has an identity: **Steelyard**, in the logo pack under
`design/`. The mark is "Counterweight", a balance beam. The palette is black
`#0A0A0A` and white only. The wordmark is Geist SemiBold, delivered as outlines.
The tagline is *"Know the true price of everything you buy."*

The repository still presents three older identities. The app calls itself
"Spend Predictor". The Streamlit dashboard and the specs say "ERP Procurement
Agent". The UI still uses a theme lifted from a third-party Framer template
("ERPSAA": sage canvas, lime `#D7FF53` accent, Outfit and Inter), with a generic
Lucide chart icon standing in for a logo. The manifest still reads
"Create TanStack App Sample". Until those are replaced, nothing the product shows
matches the brand being introduced.

## What Changes

- **Brand assets become part of the repo.** The logo pack moves from untracked
  `design/` to a tracked `brand/`, which is the source of truth. The duplicate
  loose PNGs at `design/`'s root are dropped. The web subset is copied into
  `apps/web/public`: favicon set, apple-touch icon, manifest icons, OG image.
- **The product is named Steelyard everywhere a person reads a name.** That
  covers the browser title, the sidebar, the sign-in page, the loading screen,
  the `/ui` showcase, the web manifest, the FastAPI/Scalar title, the Streamlit
  title, README, CLAUDE.md, `openspec/config.yaml` and the living specs.
- **BREAKING (UI):** the ERPSAA theme is replaced by a **monochrome token
  palette**: ink `#0A0A0A` on white surfaces, neutral greys between them, and a
  dark mode that inverts it. The lime accent is removed. The primary action
  becomes solid black, and white in dark mode. Status colours (success, warning,
  destructive, info) stay, because they carry meaning and are not brand colour.
  So do third-party ERP marks and country flags, which are other parties'
  identities.
- **BREAKING (UI):** typography moves from Outfit + Inter to **Geist** (with
  **Geist Mono** for tabular figures), matching the wordmark.
- **The logo is rendered, never retyped.** One `Logo` component draws the
  lockup and the symbol from the pack's outlined SVG paths, in `currentColor`,
  so it is black on light and white on dark. Every place that composed "icon
  tile + product name in text" uses it instead. Below 32 px it uses the
  favicon variant, which has a thicker arm.
- **BREAKING (infra):** the local PostgreSQL database, role and password
  `spend_predictor` become `steelyard`, and the compose project is named
  `steelyard`. This affects container, image and network names. A one-off
  script renames an existing dev database in place, so no data is lost.
  Every developer's `.env` `DATABASE_URL` changes.
- The package names `web-api`, `ai-api` and `mock-erp`, and the
  `ai_api.procurement_agent` module, are **not** renamed. They name what the
  code does, not the product.

## Capabilities

### New Capabilities
- `brand-identity`: where the brand assets live, the product name, how the logo
  is rendered (outlined, `currentColor`, minimum sizes, favicon variant below
  32 px), and which surfaces must carry it (title, favicon set, manifest, OG
  image, app chrome).

### Modified Capabilities
- `frontend-ui-library`: the requirement "Token-driven theming from the ERPSAA
  theme" becomes token-driven theming from the Steelyard palette. It covers the
  monochrome tokens, Geist, the removed accent, the retained status colours,
  and a visible hierarchy without a colour accent.

## Impact

- **Frontend (`apps/web`)**: `styles.css` tokens and fonts, `package.json`
  (`@fontsource-variable/geist` and `@fontsource-variable/geist-mono` added,
  Inter and Outfit removed; the **developer runs `bun add`/`bun remove`**,
  since agents do not run installs here), a new `Logo` component, and the
  sidebar, sign-in, loading screen and `/ui` showcase. `__root.tsx` head gets
  favicons, `theme-color` and OG tags. Also `public/` and `manifest.json`, plus
  the handful of components that relied on lime as a *tint*: active nav,
  selection rings, the loading glow, and `hover:brightness-95`. Snapshot and
  text assertions that name "Spend Predictor" change too.
- **Backend**: the FastAPI title, the Streamlit title, the default
  `DATABASE_URL` in `web_api/config.py` and `db/session.py`, the `alembic.ini`
  comment, and module docstrings.
- **Infra**: `docker-compose.yml` (`name: steelyard`, `POSTGRES_*`),
  `.env.example`, and a dev DB rename script. The `POSTGRES_*` variables only
  apply when a data directory is first initialised, so an existing `pgdata/`
  keeps the old names until that script runs.
- **Docs and specs**: README, CLAUDE.md, `apps/web/README.md`,
  `openspec/config.yaml` context, and name mentions in `openspec/specs/*`.
  Archived changes and historical plans keep the old names.
- **Out of scope**: renaming the repository folder or GitHub repo (which would
  also move the Claude project memory path), a marketing or landing page, and
  any external Clerk application branding. Those are follow-ups for the owner.
