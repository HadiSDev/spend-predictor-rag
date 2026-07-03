## 1. Schema & migration

- [x] 1.1 Add a `WebhookEvent` SQLModel (`provider`, unique `event_id`, `event_type`, `payload` JSON, `received_at`, `processed`, `error`) in `web_api/db/models/`
- [x] 1.2 Add `suspended_at` (nullable) to the `Organization` ORM model
- [x] 1.3 Register `WebhookEvent` in the models `__init__`
- [x] 1.4 Create one Alembic migration (new `webhook_events` table + `organizations.suspended_at`); apply to dev DB
- [x] 1.5 Confirm sync runner + existing suite unaffected (defaults applied)

## 2. Config & deps

- [x] 2.1 Add `svix` dependency; `uv sync`
- [x] 2.2 Add `CLERK_WEBHOOK_SIGNING_SECRET`, `CLERK_SECRET_KEY`, `WEB_API_CLERK_OUTBOUND_DISABLED` to `web_api/config.py` + `.env.example`

## 3. Shared provisioning refactor

- [x] 3.1 Extract find-or-create Organization/User provisioning from `deps._provision` into a reusable `web_api/clerk_sync.py` (used by both JIT and webhooks)
- [x] 3.2 Keep `deps.current_user` behavior identical (delegates to `clerk_sync`); do not resurrect suspended orgs on provision

## 4. Suspended-org access guard

- [x] 4.1 Block tenant-scoped access when `Organization.status == 'suspended'` (guard in the auth/scope chain) → `403`
- [x] 4.2 Test: suspended-org member is denied on read and management endpoints

## 5. Inbound webhook (clerk-webhooks)

- [x] 5.1 Add a Svix verifier wrapper (raw-body verification) that is injectable/overridable for tests
- [x] 5.2 `POST /api/v1/webhooks/clerk` — verify signature, reject unverified (4xx); read raw body
- [x] 5.3 Idempotency: insert `WebhookEvent` by Svix id; on conflict ack `2xx` and skip; else apply + mark processed
- [x] 5.4 Handlers: `organization.created` (provision), `organization.updated` (name/slug), `organization.deleted` (soft-suspend: `status='suspended'`, `suspended_at`)
- [x] 5.5 Handlers: `organizationMembership.created/.updated` (upsert User + role), `organizationMembership.deleted` (revoke)
- [x] 5.6 Handlers: `user.updated` (name/email), `user.deleted` (revoke); null nullable back-refs (`File.uploaded_by`) before deleting a User
- [x] 5.7 A single mapping function from Clerk payloads → domain fields (org id/slug/name, role, email)
- [x] 5.8 Wire the webhook router into the app factory

## 6. Outbound propagation (clerk-outbound-sync)

- [x] 6.1 Add `web_api/clerk_client.py`: `delete_organization(clerk_org_id)` against the Clerk Backend API using `CLERK_SECRET_KEY`; injectable + gated by `WEB_API_CLERK_OUTBOUND_DISABLED`
- [x] 6.2 `DELETE /api/v1/organization` — `require_org_admin`; soft-suspend locally (`status='suspended'`, `suspended_at`), retain data
- [x] 6.3 On local suspend/delete, propagate to Clerk (skip when no `clerk_org_id`); log + swallow outbound failure (local suspend still commits)

## 7. Tests

- [x] 7.1 Signature: valid Svix payload accepted; missing/invalid rejected (4xx)
- [x] 7.2 Idempotency: redelivered event → `2xx`, no duplicate effect; `WebhookEvent` audit row written
- [x] 7.3 Org events: created provisions; updated syncs name/slug; deleted soft-suspends and retains companies/invoices
- [x] 7.4 Suspended org blocks member access; reactivation restores it
- [x] 7.5 Membership/user events: role update reflected; membership.deleted / user.deleted revoke access; `File.uploaded_by` nulled (integrity preserved)
- [x] 7.6 Outbound: local `DELETE /organization` calls the (mocked) Clerk client; skipped when no `clerk_org_id`; disabled by config; non-admin `403`
- [x] 7.7 Loop prevention: echoed `organization.deleted` for an already-suspended org is a no-op
- [x] 7.8 Run `uv run pytest` — full suite green

## 8. Docs

- [x] 8.1 Update `CLAUDE.md` (webhook endpoint, outbound behavior, new env vars, soft-suspend semantics)
