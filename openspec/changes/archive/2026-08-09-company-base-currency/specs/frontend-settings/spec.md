## ADDED Requirements

### Requirement: A company's base currency is chosen in company settings

The company create form and the company edit form SHALL each offer a base
currency field, presented as a searchable list of ISO 4217 currencies showing
both code and name, so a user picks `DKK — Danish Krone` rather than typing a
code.

- On the create form the field SHALL be required and SHALL be submitted with the
  company; the form SHALL NOT submit without it.
- The field SHALL default to the currency implied by the selected country when
  one is known, as a pre-selection the user can change — never as a silent
  choice made on their behalf.
- The company list SHALL show each company's base currency, so a user managing
  several companies can see which currency each reports in.
- The field SHALL follow the same role gating and the same save/feedback/error
  behaviour as the other company fields.

#### Scenario: Creating a company requires a currency

- **WHEN** a user opens the create-company form and submits without choosing a
  base currency
- **THEN** the form reports the missing field and no request is sent

#### Scenario: The country pre-selects a currency

- **WHEN** the user selects Denmark as the country
- **THEN** `DKK` is pre-selected and remains freely changeable

#### Scenario: A viewer cannot change it

- **WHEN** a user without management rights opens company settings
- **THEN** the base currency is shown read-only, consistent with the other
  company fields

### Requirement: Changing the base currency prompts a recompute

When a user changes an existing company's base currency, the UI SHALL explain
that already-imported figures are still stored in the previous currency and
SHALL offer to recompute them, calling the recompute endpoint and reporting its
result.

- The explanation SHALL appear as part of confirming the change, not after the
  user has navigated away.
- While a recompute is running the control SHALL show progress and SHALL NOT be
  re-triggerable.
- The result SHALL be reported as counts of converted and still-unconverted rows,
  and a failure SHALL be surfaced with the same error treatment as other settings
  actions.
- Declining the recompute SHALL still save the currency change; the user SHALL be
  able to trigger the recompute later from the same screen.

#### Scenario: Recompute is offered on change

- **WHEN** a manager changes a company's base currency from `DKK` to `EUR` and
  confirms
- **THEN** the change is saved and the UI offers to recompute the company's
  stored figures

#### Scenario: Recompute reports what it did

- **WHEN** the user runs the recompute
- **THEN** progress is shown and the finished run reports how many rows were
  converted and how many remain unconverted

#### Scenario: Declining leaves the change in place

- **WHEN** the user declines the recompute
- **THEN** the new base currency is still saved and the recompute remains
  available from the company's settings
