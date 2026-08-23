## 1. The system-admin gate

- [x] 1.1 Add `require_system_admin` to `src/web_api/deps.py` beside `require_management` and `require_org_admin`: allows only `scope.is_system_admin`, else `403`
- [x] 1.2 Test: system admin passes; org admin, moderator, member and viewer each get `403`

## 2. The purge

- [x] 2.1 Create `src/web_api/company_deletion.py` owning both halves — the counts and the ordered delete — so the endpoint stays a thin router
- [x] 2.2 `company_records(session, company_id)`: invoice, line, posting and integration counts plus earliest/latest `accounting_date`, in one query per shape (model on `_integration_history` in `routers/erp_integrations.py:194`)
- [x] 2.3 `delete_company(session, company)`: delete in dependency order — audit rows for the company's invoices and lines, `erp_entries`, `invoice_lines`, `invoices`, `files`, `recommendations`, `sync_state`, `erp_credentials`, `erp_accounts`, `erp_integrations`, then the company. No commit: the caller owns the transaction, as `provision_integration` already does
- [x] 2.4 Collect the audit `entity_id`s **before** deleting the invoices and lines — after, there is nothing left to derive them from
- [x] 2.5 Do NOT delete `Vendor` or `SpendTree`/`SpendCategory` rows; add a comment at each site saying why, since both look like orphans afterwards
- [x] 2.6 Test: every company-scoped table is empty afterwards, asserted table by table — a forgotten table must fail here rather than leave residue
- [x] 2.7 Test: `line_ground_truth` rows go too, via the `ON DELETE CASCADE` already on `invoice_line_id` (verified present in the live schema) — `web_api` must not import `ai_api` to achieve it
- [x] 2.8 Test: a vendor referenced only by the deleted company's invoices survives
- [x] 2.9 Test: a spend tree shared with another company survives, and so does one left assigned to nothing

## 3. The endpoint

- [x] 3.1 Add `CompanyDeleteBlocked` and `CompanyDeleteResult` to `src/web_api/schemas.py` — counts plus `earliest`/`latest`, modelled on `IntegrationReplaceBlocked`
- [x] 3.2 Add `DELETE /companies/{id}` to `src/web_api/routers/companies.py` behind `require_system_admin`, taking `confirm: bool = Query(default=False)`
- [x] 3.3 Refuse with `409` and the typed body when the company holds records and `confirm` is false; delete without a gate when it holds nothing
- [x] 3.4 Wrap the delete in one transaction, rolling back on any failure
- [x] 3.5 Return the counts of what was destroyed
- [x] 3.6 Test: unconfirmed → `409` with counts and date span, and nothing removed
- [x] 3.7 Test: confirmed → company gone, `GET /companies/{id}` is `404`, and it is absent from the list even with `include_inactive=true`
- [x] 3.8 Test: an empty company deletes with no `confirm`
- [x] 3.9 Test: a system admin can delete a company in another organization; an unknown id is `404`
- [x] 3.10 Test: reports across the org no longer count the deleted company's spend

## 4. Frontend

- [x] 4.1 Add `deleteCompanyMutation` to `frontend/src/lib/companies.ts`, passing `confirm` and surfacing the `409` body so the counts reach the dialog
- [x] 4.2 Add the delete action to the company row in `settings/companies-panel.tsx`, rendered only when `principal.isSystemAdmin` — absent, not disabled
- [x] 4.3 Build the confirmation dialog: names the company, states what would be destroyed, says it cannot be undone, and points at deactivation as the reversible alternative
- [x] 4.4 Require typing the company's name to enable the confirming control
- [x] 4.5 Keep a server refusal inside the dialog rather than dismissing it
- [x] 4.6 Update the stale comment at `companies-panel.tsx:1034` — "They are soft-deactivated and never hard-deleted, so no delete" is about to be wrong
- [x] 4.7 Tests for every scenario in `specs/frontend-settings/spec.md`

## 5. Documentation

- [x] 5.1 Update `CLAUDE.md`: "Companies are soft-deactivated, never hard-deleted" now has one exception, and it belongs beside the rule rather than in a separate paragraph
- [x] 5.2 Update the comment at `src/web_api/db/models/company.py:30` for the same reason
- [x] 5.3 Update `src/web_api/deps.py`'s note about a deactivated company staying reachable by id, to say what a deleted one does instead
- [x] 5.4 Update the two test docstrings that assert the old policy in prose (`tests/web_api/test_erp_entries.py:875`, and the deactivation test in `test_management.py`)

## 6. Verification

- [ ] 6.1 `uv run pytest`
- [ ] 6.2 `cd frontend && ./node_modules/.bin/tsc --noEmit`
- [ ] 6.3 `cd frontend && ./node_modules/.bin/vitest run`
- [ ] 6.4 `cd frontend && ./node_modules/.bin/eslint src` — no new errors against the 52-problem baseline
- [ ] 6.5 Delete the `Test` company on the dev database — the 175 invoices pending against a dead mock ERP that this change exists for — and confirm an unscoped `python -m ai_api.documents.runner` no longer picks them up
