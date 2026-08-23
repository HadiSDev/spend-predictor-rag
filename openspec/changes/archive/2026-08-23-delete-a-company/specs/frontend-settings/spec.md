## ADDED Requirements

### Requirement: A system admin can delete a company from Settings

The companies list SHALL offer a delete action on each company row, shown only to
a system admin, alongside the existing deactivate action.

- A reader without the platform flag SHALL NOT see the action at all, rather than
  see it disabled. A disabled control claims a permission that will never be
  granted.
- Activating it SHALL open a confirmation naming the company and stating what
  would be destroyed — invoices, lines, postings — and that the action cannot be
  undone.
- The confirmation SHALL require typing the company's name to arm it. This is the
  only action in the product with no undo, so it is the only one that asks for
  more than a click: a checkbox is a reflex, a name is a second look at *which*
  company.
- The dialog SHALL point at deactivation as the reversible alternative, since a
  reader who wanted that and reached for this cannot tell the difference from the
  labels alone.
- A server refusal SHALL be shown in the dialog rather than dismissing it, so the
  counts arrive where the decision is being made.

#### Scenario: The action is offered to a system admin

- **WHEN** a system admin views the companies list
- **THEN** each company row offers a delete action

#### Scenario: It is absent for everyone else

- **WHEN** an org admin, moderator, member or viewer views the list
- **THEN** no delete action is rendered, disabled or otherwise

#### Scenario: The confirmation states the consequence

- **WHEN** a system admin activates the action for a company holding records
- **THEN** the dialog names the company, states what would be destroyed, and says
  the action cannot be undone

#### Scenario: The name arms the confirmation

- **WHEN** the dialog is open and the company's name has not been typed
- **THEN** the confirming control is disabled, and typing the name enables it

#### Scenario: Deactivation is offered as the reversible option

- **WHEN** the dialog is open
- **THEN** it names deactivation as the alternative that keeps the records

#### Scenario: A refusal is shown where the decision is made

- **WHEN** the server refuses the deletion
- **THEN** the dialog stays open showing the reason
