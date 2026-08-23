## ADDED Requirements

### Requirement: The sync writes an item name on every line it persists

Both line-writing paths in the sync SHALL populate `item_name`.

- **ERP bill lines**: the connector's line text SHALL be written to `item_name`.
  A bill line carries one free-text field, and it names the item; writing it to
  `description` and leaving the name null would make the always-present field the
  empty one.
- **Stand-in lines**: the posting's description SHALL be written to `item_name`,
  and SHALL be left null when the posting has none. A stand-in line is built from
  a ledger memo, which is frequently null and is sometimes only the counterparty
  name — neither is grounds for inventing a product name.
- `description` SHALL be left null by both paths. Neither source states prose
  distinct from the name, and copying the same text into both fields would make
  the distinction meaningless the moment it was introduced.

#### Scenario: An ERP bill line is named

- **WHEN** a bill line whose text is "Consulting, October" is persisted
- **THEN** the line's `item_name` is "Consulting, October" and its `description`
  is null

#### Scenario: A stand-in line from a memo is named

- **WHEN** a stand-in line is written from a posting whose description is
  "Edb-udgifter"
- **THEN** the line's `item_name` is "Edb-udgifter"

#### Scenario: A stand-in line from a memo-less posting names nothing

- **WHEN** a stand-in line is written from a posting with a null description
- **THEN** its `item_name` is null

### Requirement: The stand-in path respects fields a human has settled

The stand-in line path SHALL assign through the same verified-field guard the
ERP-line path uses, so a field a human corrected is not overwritten on the next
sync.

This path currently writes its fields directly, bypassing the guard. The result
is that a reviewer's correction to a stand-in line's text is marked verified by
the API and then silently overwritten by the next run — the guarantee the rest of
the system makes, not kept on this one path. Adding `item_name` to that path
without fixing it would extend the defect to the new field.

`--hard-reset` SHALL remain the single documented override, auditing each
overwrite as actor `system`.

#### Scenario: A corrected stand-in line survives the next sync

- **WHEN** a reviewer corrects a stand-in line's `item_name` and a sync then
  re-persists that voucher
- **THEN** the reviewer's value is still stored

#### Scenario: A hard reset still lets the ERP win

- **WHEN** the same sync is run with `--hard-reset`
- **THEN** the ERP's value replaces the reviewer's and the overwrite is audited
  as actor `system`

#### Scenario: An untouched stand-in line still refreshes

- **WHEN** a sync re-persists a stand-in line no human has corrected and the
  posting's memo has changed
- **THEN** the line's `item_name` is updated to the new memo
