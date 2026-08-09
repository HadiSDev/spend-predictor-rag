## ADDED Requirements

### Requirement: The ERP connector chooser is a branded card grid

The connector chooser in the company create and connect forms SHALL present each
connector as a card carrying its mark, its label and a one-line description,
rather than as a list of text options — choosing an ERP system is the moment a
user decides whether this product supports their accounting system.

- The grid SHALL be rendered entirely from `GET /api/v1/erp-types`. The
  front-end SHALL NOT contain a list of connector names, a per-connector branch,
  or brand text of its own; a connector registered later SHALL appear with no
  front-end change.
- A card SHALL show its connector's mark, resolved from the catalog's
  `brand_slug` against artwork vendored in the repository. Artwork SHALL NOT be
  loaded from a third-party host.
- A connector whose artwork is absent SHALL fall back to a lettered tile of the
  same size and shape. The fallback SHALL look deliberate rather than broken,
  because it is the normal state for every connector we have not drawn.
- The catalog's `description` SHALL be shown on the card when present, and the
  card SHALL omit the line rather than substituting invented text when absent.
- Selection SHALL be visibly distinct from hover and SHALL be keyboard operable
  and screen-reader labelled, since it replaces a native control.
- Choosing a connector SHALL reseed the credential inputs below from that
  connector's declared defaults, as the previous control did.
- When exactly one connector is available it SHALL still be preselected.
- The credential inputs, the edit-mode behaviour, and the fixed-once-connected
  rule for `erp_type` SHALL be unchanged: this requirement governs the chooser
  only.

#### Scenario: Connectors are presented as branded cards

- **WHEN** the company create dialog opens
- **THEN** one card per connector from `GET /api/v1/erp-types` is shown, each
  with its mark, its label, and its description when the catalog supplies one

#### Scenario: A connector with no artwork still reads as a card

- **WHEN** the catalog returns a connector whose `brand_slug` has no vendored
  artwork, or no `brand_slug` at all
- **THEN** its card shows a lettered tile in place of the mark and is otherwise
  identical to the others

#### Scenario: Choosing a card reseeds the credential fields

- **WHEN** the user selects the Billy card
- **THEN** the credential inputs below are replaced by Billy's declared fields,
  prefilled with their declared defaults, with secret fields as password inputs

#### Scenario: The grid is keyboard operable

- **WHEN** the user moves through the chooser with the keyboard and selects a
  connector
- **THEN** the selection changes, the selected card is announced as selected,
  and the form behaves as if it had been clicked

#### Scenario: No connector name is hardcoded in the front-end

- **WHEN** the catalog returns a connector the front-end has never seen
- **THEN** it is rendered as a card with the same treatment as the others,
  requiring no front-end change

#### Scenario: Submitting still sends one company request

- **WHEN** the user picks a connector from the grid, fills its credentials, and
  submits the create form
- **THEN** a single `POST /api/v1/companies` carrying the company fields and the
  `integration` block is sent, exactly as before
