## ADDED Requirements

### Requirement: The default template SHALL cover the spend an ordinary company actually books

The shipped template's leaves SHALL cover the categories a small or mid-sized European company books month to month, and SHALL include at minimum a **ground transport** leaf for rail, bus and taxi travel, a **bank and payment fees** leaf, an **insurance** leaf, and a **subscriptions and memberships** leaf, alongside the existing technology, facilities, professional services, marketing, travel, logistics and people branches.

Ground transport is named explicitly because its absence is what produced this requirement: the only travel leaves were airfare, lodging and meals, so a commuter rail ticket had no home in the platform's own default taxonomy and the categorizer was blamed for saying so. Bank fees are named because the categorizer's own documented motivating failure is a bank fee filed under telecom, and the tree it was filed against had no fees leaf either.

#### Scenario: A rail ticket has a home

- **WHEN** a company categorizes a commuter rail ticket against a freshly seeded default tree
- **THEN** the tree offers a ground-transport leaf under its travel branch

#### Scenario: A bank fee has a home

- **WHEN** a company categorizes a card or bank charge against a freshly seeded default tree
- **THEN** the tree offers a fees leaf that is not a technology or telecom node

#### Scenario: The template stays three levels and two roots

- **WHEN** the expanded template is seeded
- **THEN** every node's `level_1` is either `Direct` or `Indirect` and no node is deeper than level 3

### Requirement: A new template version SHALL NOT reach into an organization's existing copy

Raising `TEMPLATE_VERSION` SHALL affect only trees seeded **after** the raise. An organization that already holds a default-template copy SHALL NOT have nodes added to it, removed from it, or renamed within it by a template change.

The copy is the customer's, and it is editable: a node the platform adds might duplicate one they already made, and a node it renames might be one they deliberately renamed first. An organization that wants the newer taxonomy SHALL obtain it the way it obtains any other tree — by creating one — not by having theirs rewritten.

#### Scenario: An existing copy is untouched by a version bump

- **WHEN** the template version is raised and an organization already holds a copy at the previous version
- **THEN** that organization's tree has the same nodes it had before, and its recorded `template_version` is unchanged

#### Scenario: A new organization gets the new template

- **WHEN** an organization first needs a default tree after the version is raised
- **THEN** its copy is seeded from the new template and records the new version

#### Scenario: Categorized lines are unaffected

- **WHEN** the template version is raised
- **THEN** no existing line's `spend_category_id` or `level_1`..`level_4` changes and no line becomes stale
