## ADDED Requirements

### Requirement: The categorizer SHALL be told everything the ledger knows about the line

The prompt for one line SHALL carry every fact the platform holds about it: the line's **item name**, its description when it states something the name does not, the ERP account it was posted to *and that account's name*, the supplier's name *and description*, the buying company's name and description, and the amount with its currency.

The item name is the primary statement of what was bought and SHALL never be omitted when present. A field the platform does not hold SHALL be left out of the prompt entirely rather than printed as a null: a list of nulls reads to a model as evidence of absence and invites it to explain them instead of answering.

#### Scenario: The item name reaches the model

- **WHEN** a line whose `item_name` is "DSB 1' Commute20" is categorized
- **THEN** the prompt contains "DSB 1' Commute20"

#### Scenario: A name and a description are both carried

- **WHEN** a line has both an `item_name` and a `description`
- **THEN** the prompt states both, the name as what was bought and the description as further detail

#### Scenario: Absent facts are omitted, not nulled

- **WHEN** a line has no account code, no supplier and no currency
- **THEN** the prompt names none of those fields, and states only the facts that exist

### Requirement: The model SHALL choose a candidate by index and SHALL always choose one

Candidates SHALL be presented to the model as a numbered list and the reply SHALL be a number. There SHALL be no string matching between what the model wrote and what was offered, so a near-miss on spelling can never become a near-miss on category.

The model SHALL be required to return a category. Declining is withdrawn: doubt is expressed as a low confidence, not as a refusal. A model that answers with a number outside the offered range SHALL NOT have its answer snapped to the nearest candidate — that is how a misread list becomes a confident wrong answer — and the line SHALL be recorded as a genuine categorization fault instead.

#### Scenario: A valid index resolves to that node

- **WHEN** the model answers with the index of the third candidate
- **THEN** the line's `spend_category_id` names that candidate's node and its `level_1`..`level_4` come from that node's path

#### Scenario: An out-of-range index is not snapped

- **WHEN** the model answers with an index greater than the number of candidates offered
- **THEN** no category is written, the line is recorded as an AI failure, and no candidate is chosen by proximity

#### Scenario: Uncertainty is a low confidence, not a refusal

- **WHEN** the model is unsure which of two candidates fits
- **THEN** it still returns one of them, with a confidence reflecting its doubt

### Requirement: The prompt SHALL carry the accounting rules that override a literal reading

The instructions SHALL state the domain rules a management accountant applies, so the model does not categorize by surface text alone:

- A fee, tax, toll, tariff, or environmental levy SHALL be categorized as a fee or tax **regardless of which supplier issued it** — freight is explicitly not one of these.
- Packaging — boxes, pallets, wrapping — SHALL be categorized as packaging regardless of the supplier's main trade.
- A product supplied as part of a professional service SHALL follow the **service**, not the product.
- A line stating only a discount or rebate SHALL be categorized from the supplier.

The model SHALL be instructed to reason before emitting its answer, and the answer SHALL still be parsed out of the reply so the reasoning costs nothing downstream.

#### Scenario: A fee outranks its supplier's trade

- **WHEN** a line reads "Miljøtillæg" on an invoice from a freight company
- **THEN** the guidance directs it to fees and taxes rather than to logistics

#### Scenario: Reasoning precedes the answer

- **WHEN** the model replies with prose followed by its JSON answer
- **THEN** the answer is parsed successfully and the prose is discarded

### Requirement: Candidate retrieval SHALL narrow a large tree and SHALL degrade to the whole tree

When the assigned tree is large enough for it to matter, candidates SHALL be selected by embedding the line's text, retrieving the closest nodes from that tree's index, and expanding each hit to its **siblings**, so the model sees the neighbourhood of a plausible answer rather than one node from it.

Retrieval SHALL narrow only within the company's own tree. When the index is unavailable, empty, or the tree is small enough that narrowing saves nothing, the candidate set SHALL be the tree's full leaf set — **never** a different taxonomy, and never an empty list that would silently categorize nothing.

#### Scenario: A large tree is narrowed

- **WHEN** a line is categorized against a tree with several hundred leaves
- **THEN** the model is offered the retrieved neighbourhood rather than every leaf

#### Scenario: A small tree is not narrowed

- **WHEN** the tree holds fewer leaves than narrowing would remove
- **THEN** every leaf is offered and no retrieval is performed

#### Scenario: An unavailable index degrades, it does not substitute

- **WHEN** the tree has never been indexed or the vector store cannot be reached
- **THEN** the full leaf set of the company's own tree is offered and categorization proceeds

### Requirement: An identical question SHALL be answered from cache, keyed by the tree it was answered against

A categorization result SHALL be cached against the facts that produced it — the item text, the supplier, the ledger account, and a **hash of the candidate tree**. A later line with the same facts SHALL reuse the cached answer rather than calling the model again.

The tree hash is load-bearing: a customer who renames, adds or removes a node has changed what the answer means, and every cached answer against the old tree SHALL cease to match. A cached answer SHALL be indistinguishable from a fresh one on the line itself — same fields, same confidence, same rationale.

#### Scenario: A repeated purchase costs one call

- **WHEN** the same monthly commuter ticket from the same supplier is categorized twelve times against an unchanged tree
- **THEN** the model is called once and the remaining eleven lines are written from cache

#### Scenario: Editing the tree invalidates the cache

- **WHEN** a node is added to the company's tree and the same line is categorized again
- **THEN** the cached answer does not match and the model is asked afresh

#### Scenario: Another company's tree is another cache key

- **WHEN** two companies with different trees categorize an identical line
- **THEN** each is answered against its own tree and neither reads the other's cached answer

### Requirement: An unreachable model SHALL NOT be recorded as a failed line

A model that cannot be reached, or that answers text no answer can be parsed from, SHALL raise an availability error distinct from any judgement about the line. The caller SHALL leave such lines `uncategorized` so the next run picks them up.

Recording an outage as a line-level failure would bury a whole batch behind a status the sync never revisits without an explicit requeue.

#### Scenario: An outage leaves a retryable backlog

- **WHEN** the model endpoint is unreachable partway through a batch
- **THEN** the remaining lines stay `uncategorized` and the next run categorizes them

#### Scenario: An outage is distinguishable from a fault

- **WHEN** the model is unreachable
- **THEN** the error raised is distinct from the one raised when the model answers with an index that was never offered
