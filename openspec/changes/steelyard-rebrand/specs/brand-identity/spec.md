## ADDED Requirements

### Requirement: The brand source lives in the repository

The Steelyard logo pack SHALL be tracked under `brand/` as the single source of
truth (SVG, PNG, favicon and social variants, and the pack's usage rules).
Assets the web app serves SHALL be copies of files in `brand/`, never edited or
re-exported variants of them.

#### Scenario: A served asset traces to the pack

- **WHEN** any favicon, manifest icon, or OG image under `apps/web/public` is
  compared with the file of the same role in `brand/`
- **THEN** the bytes are identical

### Requirement: The product is named Steelyard

Every surface on which a person reads the product's name SHALL say
**Steelyard**: the browser title, the web manifest (`name`, `short_name`), the
app chrome, the sign-in page, the loading screen, the web API's documentation
title, the Streamlit dashboard title, and the project's README and CLAUDE.md.
"Spend Predictor", "ERP Procurement Agent" and "ERPSAA" SHALL NOT appear on any
of them.

#### Scenario: No legacy product name is shown

- **WHEN** the frontend source, the web API app factory, the Streamlit
  dashboard, README, CLAUDE.md and the living specs are searched
  case-insensitively for "spend predictor", "procurement agent" (as a product
  name) and "erpsaa"
- **THEN** there are no matches

### Requirement: The logo is rendered from its outlines, in ink

The application SHALL render the Steelyard lockup and symbol from the pack's
outlined SVG geometry through one shared `Logo` component. The wordmark SHALL
NOT be retyped as text in any font. The logo SHALL be drawn in `currentColor`
and placed only where that resolves to the ink (black on light surfaces, white
on dark), and SHALL NOT be recoloured, tinted, given effects or gradients,
tilted, or stretched.

The lockup SHALL NOT render narrower than 80 px and the symbol SHALL NOT render
smaller than 20 px. Below 32 px the symbol SHALL use the favicon geometry (the
thicker arm). Clear space around the logo SHALL be at least the diameter of the
large circle.

#### Scenario: The sidebar shows the lockup

- **WHEN** the app shell renders
- **THEN** the sidebar header shows the Steelyard lockup as SVG, with an
  accessible name of "Steelyard", and no text node containing the product name
  next to an icon

#### Scenario: The logo follows the theme

- **WHEN** the theme switches between light and dark
- **THEN** the logo is black on the light canvas and white on the dark canvas,
  with no other color

#### Scenario: Small symbol uses the favicon geometry

- **WHEN** the symbol is rendered at a size below 32 px
- **THEN** it uses the favicon variant's thicker arm

### Requirement: The web app carries the brand in its metadata

The document head SHALL link the favicon set from the pack (`favicon.ico`,
`favicon.svg`, `apple-touch-icon.png`), declare `theme-color` `#0A0A0A`, and
declare Open Graph and Twitter card metadata using the pack's
`og-image-1200x630.png`, the name "Steelyard", and the tagline "Know the true
price of everything you buy." The web manifest SHALL reference the pack's app
icons at 192 and 512 px and use `#0A0A0A` as its theme color.

#### Scenario: Favicon and share card

- **WHEN** the app's HTML head is rendered
- **THEN** it contains the three icon links, `theme-color` `#0A0A0A`, and an
  `og:image` pointing at the OG image, with `og:title` "Steelyard"

#### Scenario: Installed app icon

- **WHEN** the web manifest is read
- **THEN** its `name` and `short_name` are "Steelyard" and its icons are the
  pack's 192 and 512 px app icons

### Requirement: Local infrastructure carries the product name

The local development stack SHALL use `steelyard` as the compose project name
and as the PostgreSQL database, role and password, and every default connection
string in the code and in `.env.example` SHALL use it. An existing development
database initialised under the old name SHALL be renameable in place by a
provided script, without losing data.

#### Scenario: A fresh stack

- **WHEN** `docker compose up` initialises an empty data directory
- **THEN** a database and role named `steelyard` exist and the web API's default
  `DATABASE_URL` connects to them

#### Scenario: An existing dev database is carried across

- **WHEN** the rename script runs against a database initialised as
  `spend_predictor`
- **THEN** afterwards the database and role are `steelyard`, every existing
  table and row is present, and `alembic current` reports the same head
