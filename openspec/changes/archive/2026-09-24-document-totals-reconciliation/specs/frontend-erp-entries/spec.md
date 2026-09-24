## ADDED Requirements

### Requirement: The voucher panel SHALL show both totals when they disagree

Where an invoice's document total and its posted total differ, the panel SHALL
show **both**, labelled by source, rather than one of them.

Showing only the posted figure hides that the supplier billed something else;
showing only the document's contradicts the ledger the rest of the page is built
from. The disagreement is the finding, and a reviewer resolves it by seeing both
next to the scan — which the panel already displays.

Where they agree, or where the document stated no total, the panel SHALL show the
posted total alone. A second figure that always matches teaches the reader to
stop looking at it.

#### Scenario: A disagreement shows both figures

- **WHEN** an invoice's document total is 104,85 and its posted total is 90,00
- **THEN** the panel shows both, each labelled with where it came from

#### Scenario: Agreement shows one figure

- **WHEN** the two totals agree
- **THEN** only the posted total is shown

#### Scenario: An unread document shows one figure

- **WHEN** the document stated no total
- **THEN** only the posted total is shown, and nothing implies a comparison was
  made

#### Scenario: A charge line reads as an ordinary line

- **WHEN** a shipping charge was extracted as a line
- **THEN** it appears in the Lines tab like any other line, with its own category
  and its own controls
