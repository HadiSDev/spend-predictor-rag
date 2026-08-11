# Switching a company's ERP from the edit dialog

## Problem

The company create and edit flows are one component and one form. Name, country,
VAT number, reporting currency and spend tree are literally shared code. The
whole visual difference between "Add company" and "Edit company" sits in one
branch of `ErpConnectionFields`:

- **Create** renders `ErpTypeGrid` — one bordered card per registered connector,
  each carrying a brand mark, the connector's label and its description, with a
  primary ring on the selected one. The connector is the visual anchor of the
  section, deliberately: it is the moment a customer decides whether we support
  their accounting system.
- **Edit** renders a bare paragraph — *"Billy — connecting a different system
  replaces the integration, which is not done from here."* No mark, no card, no
  weight.

So the same decision is a row of cards in one dialog and a caption in the other.

The paragraph is also stating a product limitation as if it were a fact of life.
There is no way to move a company from one ERP to another anywhere in the
product: `PATCH /erp-integrations/{id}` accepts label and credentials only, and
`erp_type` is fixed once connected. A customer who migrates from one accounting
system to another — an ordinary event — has no path that does not involve
creating a second company.

This design makes the edit dialog's grid live, and adds the API that makes
picking a different card mean something.

## Design

### `POST /api/v1/erp-integrations/{integration_id}/replace`

Management-gated. Body is a new `IntegrationReplace(IntegrationSpec)` in
`schemas.py` — the inherited `{erp_type, label?, credentials}` plus
`confirm: bool = false`. Subclassed rather than re-declared so the credential
shape cannot drift from the two paths that already create an integration.
Returns the **new** `ErpIntegrationRead`.

In one transaction it soft-disconnects the addressed integration
(`disconnected_at = now`) and calls `provision_integration()` for the new one.
That helper already stages an integration and its encrypted credential *without
committing*, precisely so the caller can own the transaction — this is the second
caller that seam was built for, after `POST /companies`.

**Atomicity is the reason it is one endpoint.** Composing it client-side as
`disconnect` followed by `POST /erp-integrations` is two requests, and a failure
between them leaves the company connected to nothing. That is the state company
creation was designed to make impossible ("a company is never left without an ERP
connection"); a switch must not be able to produce it either. A validation
failure inside `provision_integration` rolls the whole thing back, so a rejected
switch leaves the outgoing integration connected and unchanged.

Addressed by the integration being replaced rather than by the company: it sits
with its `disconnect` / `reconnect` / `test-connection` siblings and reuses
`get_managed_integration` for tenant scoping, which gives 404-on-another-org for
free.

`erp_type` stays immutable on `PATCH`. Replacing is a different verb from
editing, and keeping the destructive one behind its own path is what stops it
being reachable by an ordinary field edit.

**Re-picking the connector already connected is not a switch.** The frontend
keeps sending today's `PATCH` (label + credentials). Only a genuinely different
`erp_type` takes this path. The endpoint enforces the same rule: an `erp_type`
equal to the current one is a 422 pointing at `PATCH`, rather than a no-op that
silently churns the integration row and resets the sync watermark.

### What happens to the data, and the confirmation that guards it

The outgoing integration keeps everything: its `ErpAccount` rows, every
`ErpEntry` posted through them, and every `Invoice` it produced. Nothing is
deleted. This is the same rule as integration disconnect and company
deactivation — financial history is retained and filtered, never destroyed.

That is right, and it creates a hazard that has to be stated where it is caused.
Invoices are keyed by connector-specific ERP ids, and nothing deduplicates across
integrations. **The new ERP re-delivering a period the old one already covered
produces a second set of rows, and both count.** For any overlapping period the
company's spend is doubled. `sync_enabled` does not help: it gates the sync fetch
and the two entry listings, and `reporting.py` is deliberately untouched by it,
so the doubled figures would reach every report.

So `replace` reports the cost before paying it, following the pattern already
used for `DELETE /spend-trees/{id}` and for spend-tree reassignment's
`stale_lines`:

- The outgoing integration brought in nothing → the switch just succeeds.
- It brought in invoices or entries → **409**, with a body carrying `invoices`,
  `entries`, and the `earliest` / `latest` `accounting_date` covered, until
  `confirm=true` is sent.

A caller who has to re-send with `confirm=true` has read the counts. Discovering
the same fact as an unexplained doubling in a report a week later is the failure
this prevents.

**How the counts are derived.** `Invoice` carries no `erp_integration_id` — only
`company_id` — so neither count can be read off a column. `ErpEntry` can be
attributed, through `erp_account_id → ErpAccount.erp_integration_id`, and that
join is the basis for both: entries are counted directly, and invoices as the
distinct non-null `source_invoice_id` among them.

The consequence is that an invoice with no posting on any of this integration's
accounts is not counted. That under-reports rather than over-reports, which is
the right direction for a number whose only job is to make the user stop and
look — and the alternative, counting every invoice on the company, would
attribute a *second* integration's invoices to the one being replaced.

The new integration is created with no `SyncState`, so the next run of
`ai_api.sync.runner` backfills it from scratch — the correct behaviour for a
system we have never read, and the reason the overlap warning matters.

### The dialog

`ErpConnectionFields`' edit branch drops the paragraph and renders the live
`ErpTypeGrid` — the same component, so the cards, brand marks, hover treatment
and `peer-checked` ring are identical to setup by construction rather than by
imitation, and a connector registered later still needs no change in this file.

Beneath the grid, the fields follow the selection:

- **Selection unchanged from `integration.erp_type`** — today's form exactly:
  the connection label, the `Replace credentials` switch, and the connector's
  credential fields only once replacement is switched on.
- **Selection changed** — the *new* connector's `credential_fields`, every
  required one required. The `Replace credentials` switch is hidden: a new
  integration has nothing stored, so "replace" is not a meaningful choice, and
  showing it off would imply credentials could be carried across. An inline
  warning names the outgoing system and what stops and starts.

Submitting a changed selection posts to `replace`. A 409 renders as a confirm
step showing the returned counts and date range; confirming re-posts with
`confirm=true`. Success invalidates the integrations query so the dialog reopens
against the new integration.

The company fields above are untouched. A submit that changes both a company
field and the connector still sends its `PATCH /companies/{id}` as today — the
two writes are independent and neither is worth entangling for this.

## Testing

**Backend** (`tests/web_api/`):

- The switch commits atomically: the old integration is `disconnected_at`-stamped,
  the new one exists with its credential encrypted, in one commit.
- A `provision_integration` 422 (unknown `erp_type`, undeclared credential key,
  missing required field) rolls back — the old integration is still connected and
  no new row exists.
- 409 with counts when the outgoing integration has invoices or entries; success
  when it has none; success with `confirm=true` in both cases.
- `erp_type` equal to the current one is 422, not a silent no-op.
- An integration in another organization is 404; a `member`/`viewer` role is 403.

**Frontend** (`companies-panel.test.tsx`):

- Edit mode renders the grid, not the paragraph, with the connected connector
  selected.
- Selecting a different connector swaps in that connector's declared fields and
  hides the `Replace credentials` switch.
- Re-selecting the current connector restores the `PATCH` form and submits a
  `PATCH`, not a `replace`.
- A 409 renders the confirm step with the counts, and confirming re-posts with
  `confirm=true`.
