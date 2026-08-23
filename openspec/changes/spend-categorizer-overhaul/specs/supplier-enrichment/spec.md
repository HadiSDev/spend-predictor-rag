## ADDED Requirements

### Requirement: A supplier's description SHALL be researched once and stored on the global vendor

The platform SHALL be able to fill `Vendor.description` with a short statement of what the supplier sells, derived from web context, and SHALL do so **once per supplier** rather than once per line or once per invoice.

The description is what turns an opaque supplier name into a categorizable fact: "DSB" is three letters, "DSB — Danish State Railways, passenger rail operator" answers the question the taxonomy is asking. `Vendor` is a **global** catalog, so one lookup serves every tenant that has ever bought from that supplier.

#### Scenario: A supplier is researched once

- **WHEN** twenty lines across four invoices name the same supplier
- **THEN** the supplier is researched at most once and all twenty lines read the stored description

#### Scenario: The description reaches the categorizer

- **WHEN** a line's supplier has a stored description
- **THEN** that description is stated in the categorization prompt alongside the supplier's name

#### Scenario: A supplier already described is not re-researched

- **WHEN** enrichment runs against a supplier whose description is already set
- **THEN** no outbound request is made and the stored description is left as it is

### Requirement: Enrichment SHALL be opt-in, and its absence SHALL degrade nothing

Supplier enrichment makes outbound requests to the public web and SHALL therefore be governed by an environment flag, defaulting to **off**, so tests and offline runs make no outbound request. This follows the rule `FX_ENABLED` already sets.

With enrichment off, or with a lookup that fails or returns nothing, the supplier's description SHALL remain null and categorization SHALL proceed on the facts that exist. A failure to describe a supplier SHALL never fail a line, an invoice, or a sync.

#### Scenario: Off by default

- **WHEN** the enrichment flag is unset
- **THEN** no outbound request is made and every vendor description stays as stored

#### Scenario: A failed lookup is not a failed line

- **WHEN** a supplier lookup times out
- **THEN** the vendor's description stays null, the line is still categorized, and the sync still completes

### Requirement: A researched description SHALL be correctable and SHALL NOT overwrite a human's

An enriched description is a machine's guess about a shared catalog row, and SHALL be treated as one. A description a human has set SHALL NOT be overwritten by a later enrichment run.

Because `Vendor` is global, a description written by enrichment is visible to every tenant, and SHALL therefore state what the supplier sells and nothing tenant-specific.

#### Scenario: A human's description stands

- **WHEN** a person has written a supplier's description and enrichment runs again
- **THEN** the stored description is unchanged

#### Scenario: The buyer's own context comes from the company, not the catalog

- **WHEN** the prompt states who bought the line
- **THEN** it draws that from the buying company, never from the global vendor row
