## ADDED Requirements

### Requirement: ERP account selection for a company

The settings area SHALL provide `/settings/companies/$companyId/accounts`, listing the company's ERP chart of accounts from `GET /api/v1/erp-integrations/{id}/accounts` with each account's code, name, type, and its two customer-owned settings — **Sync** (`sync_enabled`) and **VAT** (`with_vat`) — each toggleable via `PATCH /api/v1/erp-accounts/{id}`.

- The page SHALL be reached from the company row's action menu, and that entry
  SHALL be disabled for a company with no connected integration, since there is
  no chart to manage.
- Each toggle SHALL save on its own, immediately, without a form or a save
  button. A chart is reviewed by scanning and flipping a few switches; batching
  the changes makes a partial failure impossible to attribute.
- A failed toggle SHALL revert the switch and surface the error against that
  account, so the page never shows a setting that did not persist.
- The page SHALL explain what each toggle does: turning Sync off stops future
  ingestion and does **not** remove entries already synced, and the VAT flag
  records an assumption used when reconciling parsed invoices against posted
  entries rather than recomputing any stored amount.

#### Scenario: Accounts are listed with their settings

- **WHEN** a manager opens a connected company's accounts page
- **THEN** its ERP accounts are listed with code, name, type, and the current
  state of both toggles

#### Scenario: A toggle saves on its own

- **WHEN** a manager flips one account's Sync switch
- **THEN** only that account is patched, and the row reflects the server's result

#### Scenario: A failed toggle does not lie

- **WHEN** a toggle's request fails
- **THEN** the switch returns to its previous state and the error is shown against
  that account

#### Scenario: The action is unavailable without an integration

- **WHEN** a company has no connected ERP integration
- **THEN** the "manage accounts" entry in its action menu is disabled

### Requirement: Account list is searchable with scoped bulk actions

The accounts page SHALL provide a search over account code and name, and bulk enable/disable actions that apply **only to the accounts currently shown**.

- A bulk action SHALL state how many accounts it will affect before it is
  performed, so a filtered view cannot be mistaken for the whole chart.
- A bulk action SHALL NOT act on accounts hidden by the current search.
- The page SHALL show how many accounts exist and how many are sync-enabled.

#### Scenario: Search narrows the list

- **WHEN** a manager types part of an account code or name
- **THEN** only matching accounts are listed

#### Scenario: A bulk action is scoped to what is visible

- **WHEN** a search is active and the manager uses "disable all"
- **THEN** only the accounts matching that search are patched, and the control
  states that count beforehand

### Requirement: The account chart can be refreshed from the ERP

The accounts page SHALL offer a refresh action calling `POST /api/v1/erp-integrations/{id}/refresh-accounts`, and SHALL report what the refresh found.

- The result SHALL state how many accounts were seen and how many were newly
  added, rather than silently refetching.
- An integration whose chart has never been fetched SHALL show an empty state
  offering the refresh, not an empty table.

#### Scenario: A refresh reports what it found

- **WHEN** a manager refreshes the chart
- **THEN** the number of accounts seen and added is reported and the list updates

#### Scenario: An unfetched chart invites a refresh

- **WHEN** a company's integration has no accounts yet
- **THEN** an empty state explains this and offers to refresh from the ERP

### Requirement: Account settings are read-only without management rights

A principal without management rights SHALL see the account chart and both settings, with every control that writes disabled and the reason stated — matching that `GET .../accounts` requires only tenant scope while `PATCH /erp-accounts/{id}` and `refresh-accounts` require management.

#### Scenario: A viewer sees the chart but cannot change it

- **WHEN** a `member` or `viewer` opens the accounts page
- **THEN** the accounts and their settings are visible, and the toggles, bulk
  actions, and refresh control are disabled with the reason stated
