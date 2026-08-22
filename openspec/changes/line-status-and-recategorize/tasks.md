## 1. Backend: the requeue endpoint

- [x] 1.1 Add `RecategorizeResult` to `src/web_api/schemas.py` (`company_id`, `queued`),
      documenting that the count is lines queued, never lines categorized
- [x] 1.2 Write failing tests in `tests/web_api/test_companies.py` for the eligibility rule:
      `ai_failed` reset, `verified` / `ai_categorized` / `uncategorized` untouched and
      uncounted, and an `entry_fallback` failure reset like any other
- [x] 1.3 Write failing tests for authorization: management succeeds, `member`/`viewer`
      forbidden, another org's company `404`, a deactivated company in-org succeeds
- [x] 1.4 Write failing tests for the side effects: `error_message` cleared, one
      `requeued_for_categorization` audit row per line with actor `system` and the status
      transition, and invoice rollups recomputed
- [x] 1.5 Implement `POST /companies/{company_id}/recategorize` in
      `src/web_api/routers/companies.py` behind `require_management`, using
      `get_managed_company` for scope, `record_audit` for the trail, and
      `recompute_invoice_status` for the rollups — all in one transaction
- [x] 1.6 Verify the whole backend suite passes and the endpoint appears in `/openapi.json`

## 2. Frontend: the status column

- [x] 2.1 Add a `LineStatusBadge` component (label per status, `ai_failed` styled as the
      only problem state, meaning carried by text not colour alone, `category_stale`
      rendered as a secondary marker beside the status rather than replacing it)
- [x] 2.2 Write failing tests for the badge: four statuses render distinct labels;
      `ai_failed` and `uncategorized` are distinguishable though both show `—` for
      category; a `verified` + stale line shows both facts
- [x] 2.3 Add the Status column to `LineHeaderRow` and `LineRow` in
      `components/entries/voucher-table.tsx`
- [x] 2.4 Add the same column to the drawer's Lines tab
      (`components/entries/voucher-lines-tab.tsx`) using the shared badge
- [x] 2.5 Update `voucher-table` / `voucher-lines-tab` tests for the new column, and check
      the table still scrolls rather than overflowing the page at narrow widths

## 3. Frontend: the company menu action

- [x] 3.1 Add `RecategorizeResult` to `frontend/src/lib/types.ts` and a
      `recategorizeMutation` to `frontend/src/lib/companies.ts`, mirroring
      `recomputeFxMutation`
- [x] 3.2 Write failing tests in `components/settings/companies-panel.test.tsx`: the action
      is offered to management and absent/disabled without it; the confirmation says lines
      are queued for the next sync; the queued count is reported; a zero count says no
      failed lines were found; a failed request surfaces the error and reports no success
- [x] 3.3 Add the `onRecategorize` prop, menu item, and confirm dialog to
      `components/settings/companies-panel.tsx`, following the `RecomputeDialog` shape
- [x] 3.4 Wire the mutation in `routes/_authed/settings/companies.tsx`, invalidating nothing
      on the companies list (no company field changes) and surfacing errors through the
      section's existing feedback path
- [x] 3.5 Verify the frontend suite passes and typecheck is clean

## 4. Verify end to end

- [ ] 4.1 Against the dev database: confirm the Entries page distinguishes the 28
      `ai_failed` lines from the categorized one
- [ ] 4.2 Run the action for VectorLab ApS, confirm it reports 28 queued and that the lines
      become `uncategorized` with `error_message` cleared and audit rows written
- [ ] 4.3 Run `python -m ai_api.sync.runner --integration-id <billy>` and confirm the
      categorizer processes them (expecting most to fail again — the stub is unchanged, and
      that is the point of making the status visible)
- [x] 4.4 Update `CLAUDE.md`: the new endpoint in the endpoints list, and the
      categorization-lifecycle section noting `ai_failed` is no longer terminal
