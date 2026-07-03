## Why

Our `Organization`/`User` records are provisioned lazily — only when a user first hits the API — and never reflect deletions or renames made in Clerk. So an org deleted in Clerk still works here, a renamed org stays stale, and a removed member keeps access until their token happens to change. We need Clerk to be a live source of truth: when Clerk creates, updates, or deletes an organization (or changes memberships/users), our domain follows within seconds; and when we suspend or delete an organization on our side, Clerk follows too.

## What Changes

- Add a **Clerk webhook receiver** (`POST /api/v1/webhooks/clerk`) that verifies the Svix signature, is idempotent (each event applied at most once), and applies Clerk events to our domain:
  - `organization.created` → eagerly provision the `Organization`
  - `organization.updated` → sync `name`/`slug`
  - `organization.deleted` → **soft-suspend** (`status='suspended'`, `suspended_at` set) — financial data (companies/invoices/lines) is retained, never cascade-deleted
  - `organizationMembership.created` / `.updated` → upsert the `User` and its role
  - `organizationMembership.deleted` → revoke that user's access to the org
  - `user.updated` → sync name/email; `user.deleted` → revoke access
- Persist inbound events in a new **`WebhookEvent`** entity (idempotency key + audit trail).
- Add **outbound propagation** (us → Clerk) for the destructive direction: suspending/deleting an organization in our API calls the Clerk Backend API to delete the Clerk org. Local-origin changes are marked so the echoed webhook is a no-op (loop prevention).
- Add a `DELETE /api/v1/organization` action (system admin / org admin) that soft-suspends locally and propagates to Clerk.
- **Deferred (not in this change):** API-driven org *creation* that also creates the Clerk org — Clerk remains the creator; inbound webhook covers the create direction.

## Capabilities

### New Capabilities
- `clerk-webhooks`: the signed, idempotent inbound receiver and the handlers that apply Clerk organization / membership / user events to our domain (soft-suspend on delete).
- `clerk-outbound-sync`: propagation of locally-initiated organization suspension/deletion to Clerk via the Backend API, with echo-loop prevention.

### Modified Capabilities
- `domain-model`: add the `WebhookEvent` entity (webhook idempotency + audit); `Organization` gains `suspended_at`; define access semantics for a suspended organization and for revoked users.

## Impact

- **Schema/ORM**: new `webhook_events` table; `organizations.suspended_at` column; one Alembic migration.
- **Code** (`src/web_api/`): `routers/webhooks.py` (receiver), `clerk_sync.py` (event handlers + idempotency), `clerk_client.py` (Backend API client for outbound), `deps.py` (suspend/propagate helpers), extend the organization router with the delete/suspend action, and block suspended orgs in the auth/scope chain.
- **Dependencies**: add `svix` (webhook signature verification); outbound uses `httpx` (already present) against the Clerk Backend API.
- **Config**: `CLERK_WEBHOOK_SIGNING_SECRET` (inbound), `CLERK_SECRET_KEY` (outbound Backend API), and a toggle to disable outbound in dev/tests.
- **Tests**: signature verification (valid/invalid), idempotent redelivery, each event type, soft-suspend + access blocking, revoked-user access loss, outbound propagation (mocked Clerk client) and loop prevention.
- Auth, reads, management endpoints, sync runner, and dashboard are otherwise unaffected (except that a suspended org's members lose access).
