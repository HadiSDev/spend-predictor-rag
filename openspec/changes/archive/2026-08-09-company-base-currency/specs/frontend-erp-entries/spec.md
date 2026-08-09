## ADDED Requirements

### Requirement: Amounts are presented in the company's base currency

Amounts SHALL be presented in the company's base currency across the entries
page, its voucher groups, its postings, and the dashboard's report figures, with
the base currency mode requested from the API.

- A voucher group whose postings were made in several currencies SHALL show one
  combined total in the base currency rather than reporting mixed currencies,
  provided its postings are converted.
- Money SHALL still never be summed across currencies: when a group's postings do
  not all share one base currency, the existing mixed-currency treatment SHALL
  apply unchanged.
- When the selected scope spans companies with different base currencies, figures
  SHALL NOT be combined across them.

#### Scenario: A mixed-currency voucher shows one total

- **WHEN** a voucher's postings were made in EUR and USD for a DKK-based company
  and all are converted
- **THEN** the group shows a single DKK total instead of a mixed-currency
  indicator

#### Scenario: Base currencies are not combined across companies

- **WHEN** the current scope covers a DKK company and a EUR company
- **THEN** their figures are not added into one number

### Requirement: The original amount and the rate used are one hover away

Any amount shown converted SHALL be able to explain itself: hovering or focusing
a converted amount SHALL reveal the as-posted amount and currency, the rate
applied, and the date that rate was published for. The entry drawer SHALL show
the same information as a labelled block rather than only as a tooltip.

- The disclosure SHALL be keyboard-reachable, not hover-only.
- An amount posted in the base currency needs no disclosure and SHALL NOT show a
  rate of 1 as if it were a conversion.

#### Scenario: A converted amount explains itself

- **WHEN** the user hovers a converted total
- **THEN** the original amount and currency, the rate, and the rate date are
  shown

#### Scenario: The drawer shows the conversion in full

- **WHEN** the user opens an entry's detail drawer
- **THEN** the posted amount and currency, the base amount, the rate, and the
  rate date are all shown as labelled fields

#### Scenario: Keyboard users get the same information

- **WHEN** the user focuses a converted amount with the keyboard
- **THEN** the same disclosure appears

#### Scenario: A same-currency amount shows no conversion

- **WHEN** an entry was posted in the company's own currency
- **THEN** no rate or original-amount disclosure is offered for it

### Requirement: Amounts that could not be converted are visibly marked

A row or group carrying money that has no base-currency figure SHALL show that
money in its posted currency, visibly marked as not converted, and SHALL NOT
render it as an empty cell, a zero, or a base-currency figure.

Where the API reports how many contributing rows were unconverted, the UI SHALL
surface that the shown total is incomplete rather than presenting it as the full
figure.

#### Scenario: An unconverted posting is marked, not hidden

- **WHEN** a posting has no base amount
- **THEN** its posted amount and currency are shown with an indication that it
  is not converted

#### Scenario: An incomplete total says so

- **WHEN** a group's total excludes unconverted postings
- **THEN** the group indicates that some of its postings are not included in the
  figure

#### Scenario: Unconverted money is never shown as zero

- **WHEN** every contributing row is unconverted
- **THEN** the total is not rendered as `0.00` in the base currency
