## MODIFIED Requirements

### Requirement: Light and dark theming

The library SHALL support light (default) and dark themes via a token set toggled
by a `.dark` class on the document root, with a provider that persists the choice.
The persisted choice SHALL be a *preference* of light, dark, or **system**; when
it is `system` the provider SHALL resolve the applied theme from the operating
system's colour-scheme setting and SHALL follow that setting while it remains
`system`. Consumers SHALL be able to read both the resolved theme and the stored
preference, so a control can show what the user actually chose rather than what
is currently displayed.

#### Scenario: Dark mode swaps tokens

- **WHEN** the dark theme is active
- **THEN** canvas/surface/ink tokens invert while the accent stays consistent

#### Scenario: System preference follows the OS

- **WHEN** the stored preference is `system`
- **THEN** the applied theme matches the operating system's colour scheme, and it
  changes with the OS setting without a reload

#### Scenario: Preference survives a reload

- **WHEN** the user picks a preference and reloads
- **THEN** the same preference is in effect, and a `system` preference is not
  flattened into the light or dark value it happened to resolve to
