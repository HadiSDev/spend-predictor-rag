## 1. Preflight

- [x] 1.1 Confirm `git status` shows only `design/` untracked and no uncommitted edits under `apps/web`, `apps/web-api`, `docker-compose.yml` or `.env.example`. Stop and ask if another agent is mid-edit there.
- [x] 1.2 Record the baselines: `uv run pytest -q` counts, `./node_modules/.bin/vitest run` counts in `apps/web`, the ESLint problem count, and a clean `tsc --noEmit`
- [x] 1.3 Take "before" screenshots (dashboard, entries with the voucher panel open, settings → companies, sign-in; light and dark) for the final comparison. The user runs the dev servers; ask for the URL rather than launching them.

## 2. Brand assets

- [x] 2.1 Byte-compare `design/*.png` (root) with their pack counterparts. Move `design/steelyard-logo-pack/steelyard-logo-pack/*` to `brand/` (flattening the doubled folder), and drop the root duplicates and the now-empty `design/`.
- [x] 2.2 Copy `favicon.ico`, `favicon.svg`, `apple-touch-icon.png`, `favicon-192.png`, `favicon-512.png` and `og-image-1200x630.png` into `apps/web/public`. Delete `logo192.png` and `logo512.png`.
- [x] 2.3 Rewrite `apps/web/public/manifest.json`: name and short_name "Steelyard", icons `favicon-192.png` / `favicon-512.png`, `theme_color` and `background_color` per design Decision 6
- [x] 2.4 Add a vitest asserting that each public brand file is byte-equal to its `brand/` source

## 3. Logo component

- [x] 3.1 Create `apps/web/src/components/brand/logo.tsx`: `variant` lockup | symbol, `currentColor` fills, geometry copied verbatim from `steelyard-symbol-black.svg`, `favicon.svg` (below 32 px) and `steelyard-lockup-black.svg`. It has `role="img"` and `aria-label="Steelyard"`, and clamps to 80 px for the lockup and 20 px for the symbol.
- [x] 3.2 Tests: accessible name, the favicon geometry below 32 px, minimum clamping, and every fill is `currentColor`
- [x] 3.3 Replace the composed "tile + Spend Predictor" in `app-shell.tsx`, `routes/sign-in.tsx`, `ui/loading-screen.tsx` and `routes/ui.tsx` with `<Logo>`. Keep the org switcher's alignment comment accurate (`org-switcher.tsx`).
- [x] 3.4 Tests: the app shell, sign-in and loading screen expose the logo by name "Steelyard", and no text node spells the product name

## 4. Monochrome tokens

- [x] 4.1 Replace the `:root` and `.dark` values in `apps/web/src/styles.css` with the Decision 3 palette. Update the header comment (drop ERPSAA and the Framer URL). Keep status tokens, and retune them only if a contrast check fails.
- [x] 4.2 Retint the react-day-picker variables and selected-day rule to ink (Decision 4)
- [x] 4.3 Contrast check: compute the ratios for foreground/muted/subtle on card and canvas, primary-foreground on primary, and each status pair, in both themes. All body-text pairs must be ≥ 4.5:1. Record the table in the change folder.
- [x] 4.4 Tint fixes (Decision 4): active nav in `ui/layout/sidebar.tsx`, the connector choice card in `settings/companies-panel.tsx`, the preferences pills, the loading glow removal, `button.tsx` hover, and the `card.tsx` stat tile. Check `badge.tsx`, `progress`, `radio`, `checkbox`, `switch` and `tree-selector.tsx` still read correctly with an ink primary.
- [x] 4.5 Update the "ERPSAA" comments in `ui/index.ts`, `ui/calendar.tsx` and `apps/web/README.md`
- [x] 4.6 Add a vitest source scan: no `#d7ff53`, `#e9ecea` or `#091315` (case-insensitive), and no "spend predictor" or "erpsaa", anywhere under `apps/web/src`

## 5. Typography

- [x] 5.1 **Ask the user to run** `cd apps/web && bun add @fontsource-variable/geist @fontsource-variable/geist-mono && bun remove @fontsource-variable/inter @fontsource-variable/outfit`. Never run it, and never use npm or pnpm. Wait for confirmation.
- [x] 5.2 Swap the `@import`s and the `--font-sans`/`--font-display`/`--font-mono` tokens in `styles.css` to Geist / Geist Mono
- [x] 5.3 Apply `font-mono` to money columns in the data tables where figures must align (entries lines, voucher totals, reports). Check that `tabular-nums` is still present.

## 6. Document head

- [x] 6.1 `routes/__root.tsx` `head()`: title "Steelyard", icon links (`favicon.ico` 48x48, `favicon.svg`, `apple-touch-icon.png`), manifest link, `theme-color` `#0A0A0A`, `og:title`/`og:description` (tagline)/`og:image`/`og:type`, and `twitter:card` `summary_large_image`
- [x] 6.2 Test: the head descriptor contains the title, the three icon links, theme-color and og:image

## 7. Backend names and docs

- [x] 7.1 FastAPI title "Steelyard Web API" (`web_api/app.py`). Streamlit `page_title`/`st.title` "Steelyard" (`dashboard/app.py`). The docstrings in `ai_api/sync/runner.py` and `dashboard/app.py`, and the `alembic.ini` header comment.
- [x] 7.2 CLAUDE.md: the product heading and intro (Steelyard, with the one-line tagline), plus a short "Brand" section stating where `brand/` lives, the `Logo` component rule (rendered, never retyped), and monochrome with status as the only hue
- [x] 7.3 README.md title and intro, and the `openspec/config.yaml` context line naming the product
- [x] 7.4 Living specs: replace "ERP Procurement Agent" as the product name in `openspec/specs/domain-model/spec.md`. Leave "procurement agent" where it names the recommender feature.

## 8. Infrastructure rename

- [x] 8.1 `docker-compose.yml`: top-level `name: steelyard`, and `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD` set to `steelyard`
- [x] 8.2 The default `DATABASE_URL` in `web_api/config.py` and `web_api/db/session.py`, and `.env.example`, move to `steelyard`
- [x] 8.3 Write `scripts/rename-dev-db.sh` per Decision 7: `--from`/`--to` defaulting to spend_predictor → steelyard, refusal while connections exist, idempotent. Test it against a throwaway container (`docker run postgres:16` initialised as `spend_predictor`, seeded with one table and row): the rename succeeds, the row survives, and a second run is a no-op.
- [x] 8.4 CLAUDE.md "Infra" bullet: the new names, the one-time migration steps (Migration Plan step 3), and a note that `POSTGRES_*` only applies to a fresh `pgdata/`
- [x] 8.5 Hand the user the migration steps. **Do not** run them against their dev database or edit their `.env` or any worktree `.env` (`.claude/worktrees/*`, `.kilo/worktrees/*`).

## 9. Verify and land

- [x] 9.1 `uv run pytest -q` passes the baseline count (the migration test skips or runs according to the user's DB state after 8.5). Vitest passes the baseline plus the new tests, ESLint shows no new problems, and `tsc --noEmit` is clean.
- [x] 9.2 Run `git grep -niE "spend.?predictor|erpsaa|d7ff53"` outside `openspec/changes/archive`, `docs/superpowers` and lockfiles. Matches may remain only in `scripts/rename-dev-db.sh` (the old name is its input) and the CLAUDE.md migration note.
- [x] 9.3 "After" screenshots matching 1.3, in both themes. Show them to the user side by side with the "before" set, and get their verdict on visual weight before committing.
- [x] 9.4 Commit in two commits (brand + UI + names, then infra), and list the user's one-time migration steps in the second commit's message
