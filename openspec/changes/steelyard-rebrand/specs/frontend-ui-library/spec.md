## RENAMED Requirements

- FROM: `### Requirement: Token-driven theming from the ERPSAA theme`
- TO: `### Requirement: Token-driven theming from the Steelyard palette`

## MODIFIED Requirements

### Requirement: Token-driven theming from the Steelyard palette

The UI library SHALL define a single design-token layer (Tailwind v4 `@theme`
CSS variables) reproducing the **Steelyard** palette, and every component SHALL
derive its colors, typography, radius, and spacing from those tokens rather than
hard-coded values.

The palette is **monochrome**: ink `#0A0A0A` on white surfaces, with neutral
(hue-free) greys for canvas, muted surfaces, borders and secondary text. The
primary action color SHALL be the ink itself — solid `#0A0A0A` with white text
in light mode, and white with `#0A0A0A` text in dark mode. There SHALL be no
brand accent color: the former lime `#D7FF53`, the sage canvas `#E9ECEA` and the
ink `#091315` SHALL NOT appear anywhere in the application's styles.

Semantic status colors — success, warning, destructive, info — SHALL remain,
because they carry meaning (a failed posting, a rejected document) that
monochrome cannot. They SHALL be used only for status, never as decoration or
emphasis. Third-party marks (ERP connector artwork) and country flags are other
parties' identities and are exempt.

Typography SHALL be **Geist** for display and body text and **Geist Mono** for
tabular figures, matching the wordmark. Inter and Outfit SHALL NOT be loaded.

Without a color accent, hierarchy SHALL come from contrast and weight: the
active navigation item and the selected state of a choice control SHALL be
visibly distinct from their neighbours by more than a faint tint of grey (for
example an inverted ink fill, or an ink border plus weight). Hover states SHALL
produce a visible change on an ink-filled control, which a brightness filter on
near-black does not.

#### Scenario: Components consume tokens

- **WHEN** a component renders
- **THEN** its colors/radii/fonts come from theme tokens, so changing a token in
  one place restyles the component

#### Scenario: Theme reflects the brand

- **WHEN** the library is rendered in light mode
- **THEN** the primary button is `#0A0A0A` with white text, surfaces are white,
  text is set in Geist, and no lime, sage or other hued brand color is present

#### Scenario: Dark mode inverts the ink

- **WHEN** the library is rendered in dark mode
- **THEN** the canvas is near-black, text and the primary button are white, and
  the primary button's text is `#0A0A0A`

#### Scenario: Status keeps its color

- **WHEN** a destructive action, a failed status, or a warning is rendered
- **THEN** it uses the corresponding status token, and that is the only hue on
  screen that is not part of a third-party mark or flag

#### Scenario: The active item stands out without an accent

- **WHEN** the sidebar renders with one item active
- **THEN** the active item is distinguished by an ink fill or ink border and
  weight, not by a low-opacity tint alone
