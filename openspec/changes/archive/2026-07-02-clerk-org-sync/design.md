## Context

The web API treats Clerk as the identity/org source but only mirrors it lazily (JIT on first request) and one-directionally — it never learns about deletions, renames, or membership changes, and can't reflect a local org teardown back to Clerk. Clerk delivers state changes as signed webhooks (via Svix). This change adds a signed, idempotent inbound receiver that keeps our domain in sync, plus outbound propagation of the destructive direction (suspend/delete) back to Clerk. It builds on the archived `web-api-clerk-review` and `org-company-management` specs (JIT provisioning, roles, `Organization.status`).

## Goals / Non-Goals

**Goals:**
- Signed (Svix), idempotent `POST /api/v1/webhooks/clerk` applying org / membership / user events.
- `organization.deleted` → soft-suspend (retain all financial data); suspended orgs block access.
- Outbound: suspending/deleting an org locally deletes the Clerk org via the Backend API, with echo-loop prevention.
- Proper persistence: a `WebhookEvent` idempotency/audit model and `Organization.suspended_at`.
- Testable with no live Clerk (injected verifier + mocked Clerk client).

**Non-Goals:**
- API-driven org *creation* that also creates the Clerk org (Clerk stays the creator; inbound covers create).
- Two-way sync of companies/invoices (those are ours alone).
- Retrying/queuing failed outbound calls beyond a best-effort call + logged failure (a durable queue is future work).

## Decisions

### Verify Svix signatures with the `svix` library; the signature is the auth
The webhook route is unauthenticated by JWT — it authenticates by verifying the `svix-id`/`svix-timestamp`/`svix-signature` headers against `CLERK_WEBHOOK_SIGNING_SECRET` using `svix.webhooks.Webhook`. Verification happens on the raw request body (not the parsed JSON) since the signature covers exact bytes. The verifier is injected so tests can substitute a fake. Alternative — hand-rolled HMAC — was rejected: Svix's scheme (timestamp tolerance, versioned signatures) is easy to get subtly wrong.

### Idempotency + audit via a `WebhookEvent` table keyed by Svix id
Every accepted event is recorded by its Svix message id (unique). Processing is: verify → insert `WebhookEvent` (unique id) → on insert-conflict, ack as already-processed and stop → else apply handler in the same transaction → mark processed. This makes redelivery a no-op and gives an audit trail. The unique constraint is the idempotency guard even under concurrent redelivery.

### Handlers reuse existing provisioning; deletion is soft-suspend
`organization.created/updated` reuse the find-or-create logic from `deps._provision`, refactored into a reusable `clerk_sync` module so both the JIT path and webhooks share one implementation. `organization.deleted` sets `status='suspended'` + `suspended_at` — never a cascade delete — honoring "retain financial data." Membership events upsert/remove `User`; `organizationMembership.deleted`/`user.deleted` revoke access by deleting the `User` row after nulling nullable back-references (`File.uploaded_by`), preserving referential integrity.

### Suspended orgs are blocked in the existing auth chain
`current_user`/`tenant_scope` (or a small guard after them) rejects requests whose `Organization.status == 'suspended'` with `403`. Centralizing it there means every tenant-scoped endpoint is covered without per-route checks. JIT provisioning will not "resurrect" a suspended org: provisioning updates fields but leaves `status` as-is.

### Outbound is a thin Clerk Backend API client, gated and loop-safe
A `clerk_client` wraps `DELETE https://api.clerk.com/v1/organizations/{clerk_org_id}` with `CLERK_SECRET_KEY`. It is invoked when an org is suspended/deleted locally (the new `DELETE /api/v1/organization`). `WEB_API_CLERK_OUTBOUND_DISABLED` (default true in tests) short-circuits it. Loop prevention is structural, not stateful: the echoed `organization.deleted` webhook hits an already-suspended org, and the idempotent/soft handler makes it a no-op — so no extra "origin" bookkeeping is required. Outbound failure is logged; local suspension still commits (Clerk deletion can be retried/managed out of band).

### One additive migration
New `webhook_events` table; `organizations.suspended_at` column (nullable). Additive and backfill-safe; existing rows and synthetic tenants unaffected.

## Risks / Trade-offs

- **Signature verification on parsed vs raw body** → read the raw body in the route and verify before JSON parsing; test with a real Svix-signed payload.
- **Outbound failure leaves Clerk and us divergent** → local suspend is source-of-truth for access; log the failed Clerk call for retry. Acceptable because access is already revoked locally.
- **Accidental access loss from a spurious delete event** → soft-suspend is reversible; a subsequent restore/`created` event or explicit reactivate clears `suspended_at`. No data is destroyed.
- **User deletion vs FK references** → null nullable references (`File.uploaded_by`) before deleting the `User`; covered by a test.
- **Webhook ordering / races** (e.g. membership before org exists) → handlers find-or-create the org as needed and are order-independent where feasible; unresolved references are logged on the `WebhookEvent`.

## Migration Plan

1. Add `WebhookEvent` model + `Organization.suspended_at`; generate + apply one Alembic migration.
2. Add config (`CLERK_WEBHOOK_SIGNING_SECRET`, `CLERK_SECRET_KEY`, `WEB_API_CLERK_OUTBOUND_DISABLED`) and the `svix` dependency.
3. Refactor provisioning into `clerk_sync`; add webhook receiver router + event handlers; add the suspended-org access guard.
4. Add `clerk_client` + `DELETE /api/v1/organization`; wire outbound propagation.
5. Tests (verification, idempotency, each event, suspend/block, revoke, outbound mocked, loop no-op). Run `uv run pytest`.
Rollback: additive — remove the webhook/outbound routers and revert the migration; JIT provisioning and existing endpoints keep working.

## Open Questions

- Exact Clerk event payload field paths (org id/slug/name, membership role, user email) — confirm against real Clerk webhook samples during implementation; keep extraction in one mapping function.
- Whether a future change adds a durable retry queue for outbound calls (out of scope here).
