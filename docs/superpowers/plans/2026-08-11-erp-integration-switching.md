# ERP Integration Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a management user move a company from one ERP to another from the company edit dialog, replacing the static connector caption with the same live brand-card grid the setup flow uses.

**Architecture:** One new endpoint, `POST /api/v1/erp-integrations/{id}/replace`, soft-disconnects the addressed integration and provisions the replacement in a single transaction, 409ing with the ledger counts it would double until `confirm=true`. The frontend's `ErpConnectionFields` edit branch renders the existing `ErpTypeGrid` live instead of a paragraph, and follows the selection with either today's PATCH form or the new connector's credential fields.

**Tech Stack:** FastAPI + SQLModel + Pydantic (backend, `pytest`); React + TanStack Query + react-hook-form + Tailwind (frontend, `vitest`).

**Spec:** `docs/superpowers/specs/2026-08-11-erp-integration-switching-design.md`

## Global Constraints

- Python 3.12, managed with `uv`. Run tests with `uv run pytest`.
- Frontend uses **bun**; `bun.lock` is committed. **Never run a package-manager install.** Call binaries directly: `./node_modules/.bin/vitest`.
- `web_api` must never import `ai_api`. The dependency runs one way only.
- `web_api/spend_trees/service.py` is the only writer of `SpendCategory`. Nothing in this plan touches it.
- Money is never summed across currencies. Nothing in this plan sums money.
- Integrations are **soft**-disconnected (`disconnected_at`), never deleted. Companies are soft-deactivated. No task here deletes a financial row.
- Work directly on `main`. Commit after each task.

---

### Task 1: The `replace` endpoint — happy path, same-type refusal, atomic rollback

**Files:**
- Modify: `src/web_api/schemas.py` (add `IntegrationReplace` after `IntegrationSpec`)
- Modify: `src/web_api/routers/erp_integrations.py` (add endpoint after `reconnect_integration`, ~line 190)
- Test: `tests/web_api/test_erp_integrations.py`

**Interfaces:**
- Consumes: `provision_integration(session, company_id, spec) -> ErpIntegration` from `web_api/integrations.py` — stages an integration and its encrypted credential **without committing**, raising 422 before adding anything if the connector or credentials are invalid. `get_managed_integration(session, scope, integration_id) -> ErpIntegration` from `web_api/deps.py` — 404s if out of the caller's tenant scope.
- Produces: `POST /api/v1/erp-integrations/{integration_id}/replace`, body `IntegrationReplace`, returns `ErpIntegrationRead` of the **new** integration with 201. Task 2 adds the 409 branch to this same endpoint; Task 3 calls it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/web_api/test_erp_integrations.py`. Read the top of that file first for the existing fixtures (`client`, `auth`, and how a company + integration are seeded) and match them — the names below assume a `client` fixture and an `auth(token)` header helper, as the rest of the file uses.

```python
def test_replace_disconnects_the_old_and_connects_the_new(client, engine):
    """A switch is one transaction: the old is retired, the new is live."""
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Switcher",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()
    old_id = company["integration"]["id"]

    response = client.post(
        f"/api/v1/erp-integrations/{old_id}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "label": "Billy main",
              "credentials": {"access_token": "tok_live"}},
    )

    assert response.status_code == 201, response.text
    new = response.json()
    assert new["id"] != old_id
    assert new["erp_type"] == "billy"
    assert new["label"] == "Billy main"
    assert new["has_credentials"] is True
    assert new["disconnected_at"] is None

    old = client.get(f"/api/v1/erp-integrations/{old_id}", headers=auth("tokA")).json()
    assert old["disconnected_at"] is not None, "the outgoing integration must be retired"


def test_replacing_with_the_same_erp_type_is_422(client):
    """Not a switch. PATCH edits label and credentials; this would only churn."""
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Same",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()
    integration_id = company["integration"]["id"]

    response = client.post(
        f"/api/v1/erp-integrations/{integration_id}/replace",
        headers=auth("tokA"),
        json={"erp_type": "mock", "credentials": {}},
    )

    assert response.status_code == 422
    assert "PATCH" in response.json()["detail"]


def test_a_rejected_replacement_leaves_the_old_integration_connected(client):
    """Atomicity: a 422 from the new connector must not retire the old one.

    This is the failure the single endpoint exists to prevent — a client-side
    disconnect-then-create would leave the company connected to nothing.
    """
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Rollback",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()
    old_id = company["integration"]["id"]

    response = client.post(
        f"/api/v1/erp-integrations/{old_id}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "credentials": {"nonsense_key": "x"}},
    )
    assert response.status_code == 422

    old = client.get(f"/api/v1/erp-integrations/{old_id}", headers=auth("tokA")).json()
    assert old["disconnected_at"] is None, "a rejected switch must change nothing"

    listed = client.get("/api/v1/erp-integrations", headers=auth("tokA")).json()
    assert [i["id"] for i in listed if i["company_id"] == company["id"]] == [old_id]


def test_replace_requires_a_management_role(client):
    """A viewer must not be able to retire a company's ERP connection."""
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Gated",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()

    response = client.post(
        f"/api/v1/erp-integrations/{company['integration']['id']}/replace",
        headers=auth("tokViewer"),  # a member/viewer principal in the same org
        json={"erp_type": "billy", "credentials": {"access_token": "t"}},
    )
    assert response.status_code == 403


def test_replace_on_another_orgs_integration_is_404(client):
    """Tenant scope comes from get_managed_integration; assert it is applied."""
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Mine",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()

    response = client.post(
        f"/api/v1/erp-integrations/{company['integration']['id']}/replace",
        headers=auth("tokB"),  # a principal in a different organization
        json={"erp_type": "billy", "credentials": {"access_token": "t"}},
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/web_api/test_erp_integrations.py -k replace -v`
Expected: FAIL — all five 404, because the route does not exist yet.

`auth("tokB")` and `auth("tokViewer")` are placeholders for the file's real principals. This file already has cross-org and 403 role tests (see the assertions around lines 141 and 304 of `tests/web_api/test_erp_integrations.py`) — read how they obtain a second organization's principal and a non-manager, and use exactly those. Do not invent a fixture.

- [ ] **Step 3: Add the request schema**

In `src/web_api/schemas.py`, directly after `class IntegrationSpec`:

```python
class IntegrationReplace(IntegrationSpec):
    """Replace a company's ERP connection with a different system.

    Subclasses `IntegrationSpec` rather than re-declaring its fields so the
    credential shape cannot drift from the two paths that already create an
    integration.

    `confirm` acknowledges that the outgoing integration's ledger data stays and
    the new ERP will re-deliver overlapping periods as separate rows. Required
    only when there is such data — see the 409 body.
    """

    confirm: bool = False
```

- [ ] **Step 4: Add the endpoint**

In `src/web_api/routers/erp_integrations.py`, add `IntegrationReplace` to the `..schemas` import block, then add this immediately after `reconnect_integration`:

```python
@router.post(
    "/erp-integrations/{integration_id}/replace",
    response_model=ErpIntegrationRead,
    status_code=status.HTTP_201_CREATED,
)
def replace_integration(
    integration_id: str,
    body: IntegrationReplace,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> ErpIntegrationRead:
    """Move a company to a different ERP: retire the old, connect the new, once.

    One transaction on purpose. Composed client-side as disconnect-then-create,
    a failure between the two calls would leave the company connected to
    nothing — the state `POST /companies` was built to make impossible.

    The outgoing integration keeps every account, entry and invoice it produced;
    it is soft-disconnected, exactly as `/disconnect` leaves it.
    """
    outgoing = get_managed_integration(session, scope, integration_id)

    if body.erp_type == outgoing.erp_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"This company is already connected to {outgoing.erp_type!r}. "
                "Use PATCH /erp-integrations/{id} to change its label or "
                "credentials; replacing would retire the integration and "
                "restart its sync from scratch."
            ),
        )

    try:
        outgoing.disconnected_at = _now()
        session.add(outgoing)
        incoming = provision_integration(
            session,
            outgoing.company_id,
            IntegrationSpec(
                erp_type=body.erp_type,
                label=body.label,
                credentials=body.credentials,
            ),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(incoming)
    return _read(incoming)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/web_api/test_erp_integrations.py -k replace -v`
Expected: PASS, 4 tests.

Then the whole file, to catch anything the new route shadowed:
Run: `uv run pytest tests/web_api/test_erp_integrations.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web_api/schemas.py src/web_api/routers/erp_integrations.py tests/web_api/test_erp_integrations.py
git commit -m "feat(api): replace a company's ERP integration in one transaction"
```

---

### Task 2: The 409 that reports what a switch would double

**Files:**
- Modify: `src/web_api/schemas.py` (add `IntegrationReplaceBlocked`)
- Modify: `src/web_api/routers/erp_integrations.py` (add `_integration_history`, extend `replace_integration`)
- Modify: `CLAUDE.md` (document the endpoint under "ERP connectors")
- Test: `tests/web_api/test_erp_integrations.py`

**Interfaces:**
- Consumes: `replace_integration` from Task 1; `ErpAccount.erp_integration_id`, `ErpEntry.erp_account_id`, `ErpEntry.source_invoice_id`, `ErpEntry.accounting_date` from `web_api/db/models`.
- Produces: 409 with body `{"detail": str, "invoices": int, "entries": int, "earliest": str | None, "latest": str | None}` under FastAPI's `detail` envelope. Task 5 renders these fields.

**Why the counts are a join, not a column:** `Invoice` carries no `erp_integration_id` — only `company_id`. `ErpEntry` reaches its integration through `erp_account_id → ErpAccount.erp_integration_id`, so entries are counted directly and invoices as the distinct non-null `source_invoice_id` among them. An invoice with no posting on this integration's accounts is therefore not counted; that under-reports, which is the safe direction for a number whose only job is to make someone stop and look.

- [ ] **Step 1: Write the failing tests**

```python
def test_replace_409s_with_counts_when_the_old_integration_has_ledger_data(
    client, engine, seed_switchable_ledger
):
    """The cost is reported at the moment it is caused, not found in a report later."""
    old_id, expected = seed_switchable_ledger

    response = client.post(
        f"/api/v1/erp-integrations/{old_id}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "credentials": {"access_token": "t"}},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["entries"] == expected["entries"]
    assert detail["invoices"] == expected["invoices"]
    assert detail["earliest"] == "2026-01-05"
    assert detail["latest"] == "2026-03-20"

    old = client.get(f"/api/v1/erp-integrations/{old_id}", headers=auth("tokA")).json()
    assert old["disconnected_at"] is None, "a blocked switch must change nothing"


def test_replace_proceeds_with_confirm_true(client, seed_switchable_ledger):
    """Confirming is the acknowledgement; nothing is deleted by it."""
    old_id, _ = seed_switchable_ledger

    response = client.post(
        f"/api/v1/erp-integrations/{old_id}/replace",
        headers=auth("tokA"),
        json={
            "erp_type": "billy",
            "credentials": {"access_token": "t"},
            "confirm": True,
        },
    )

    assert response.status_code == 201, response.text
    old = client.get(f"/api/v1/erp-integrations/{old_id}", headers=auth("tokA")).json()
    assert old["disconnected_at"] is not None


def test_replace_needs_no_confirmation_when_nothing_was_synced(client):
    """A never-synced integration has no history to double, so do not nag."""
    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Fresh",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()

    response = client.post(
        f"/api/v1/erp-integrations/{company['integration']['id']}/replace",
        headers=auth("tokA"),
        json={"erp_type": "billy", "credentials": {"access_token": "t"}},
    )
    assert response.status_code == 201, response.text
```

Add the fixture in the same file. It seeds one company whose integration has an account carrying three entries across two invoices:

```python
@pytest.fixture
def seed_switchable_ledger(client, engine):
    """A company + integration with ledger history, and the counts to expect.

    Written through the ORM rather than the API because no endpoint creates
    entries — the sync runner does, and `web_api` cannot import it.
    """
    import datetime as dt

    from sqlmodel import Session

    from web_api.db.models import ErpAccount, ErpEntry, Invoice

    company = client.post(
        "/api/v1/companies",
        headers=auth("tokA"),
        json={
            "name": "Historied",
            "base_currency": "DKK",
            "integration": {"erp_type": "mock", "credentials": {}},
        },
    ).json()
    integration_id = company["integration"]["id"]

    with Session(engine) as session:
        account = ErpAccount(
            company_id=company["id"],
            erp_integration_id=integration_id,
            erp_account_code="6000",
            erp_account_name="Consulting",
        )
        session.add(account)
        invoices = []
        for n in (1, 2):
            invoice = Invoice(company_id=company["id"], status="uncategorized", source="erp")
            invoices.append(invoice)
            session.add(invoice)
        session.add_all(
            [
                ErpEntry(
                    company_id=company["id"],
                    erp_account_id=account.id,
                    source_invoice_id=invoices[0].id,
                    accounting_date=dt.date(2026, 1, 5),
                ),
                ErpEntry(
                    company_id=company["id"],
                    erp_account_id=account.id,
                    source_invoice_id=invoices[1].id,
                    accounting_date=dt.date(2026, 3, 20),
                ),
                # No source invoice: counts as an entry, not as an invoice.
                ErpEntry(
                    company_id=company["id"],
                    erp_account_id=account.id,
                    source_invoice_id=None,
                    accounting_date=dt.date(2026, 2, 1),
                ),
            ]
        )
        session.commit()

    return integration_id, {"entries": 3, "invoices": 2}
```

If `ErpAccount` or `ErpEntry` require fields not set above (check `src/web_api/db/models/erp_account.py` and `erp_entry.py` for `nullable=False` columns without defaults), add the minimum needed — do not change the models.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/web_api/test_erp_integrations.py -k "409 or confirm or nothing_was_synced" -v`
Expected: the 409 test FAILS with `assert 201 == 409`; the confirm test may already pass (it asserts 201, which Task 1 gives). That is fine — it becomes a real guard once the 409 exists.

- [ ] **Step 3: Add the 409 body schema**

In `src/web_api/schemas.py`, after `IntegrationReplace`:

```python
class IntegrationReplaceBlocked(BaseModel):
    """Why a replacement needs confirming: what the outgoing ERP already posted.

    Nothing here is deleted by the switch. The hazard is the opposite — the rows
    stay, the new ERP re-delivers the same periods as separate rows, and no
    report can tell the two apart.
    """

    detail: str
    invoices: int
    entries: int
    earliest: date | None = None
    latest: date | None = None
```

`date` is already imported in `schemas.py` — confirm with `grep -n "^from datetime" src/web_api/schemas.py` and add it to that import if not.

- [ ] **Step 4: Add the history query and the 409 branch**

In `src/web_api/routers/erp_integrations.py`, add `ErpEntry` to the `web_api.db.models` import and add `from sqlalchemy import func` — that is where `reporting.py` and `routers/erp_entries.py` both take it from, and this file has no `sqlalchemy` import yet. Add above `replace_integration`:

```python
def _integration_history(session: Session, integration: ErpIntegration) -> dict:
    """What this integration has posted: entry count, invoice count, date span.

    Reached through `ErpAccount`, because `ErpEntry` carries no integration of
    its own and `Invoice` carries none at all. Invoices are the distinct
    `source_invoice_id` among those entries, so an invoice with no posting on
    this integration's accounts is not counted — under-reporting, which is the
    safe direction here.
    """
    account_ids = select(ErpAccount.id).where(
        ErpAccount.erp_integration_id == integration.id
    )
    row = session.exec(
        select(
            func.count(ErpEntry.id),
            func.count(func.distinct(ErpEntry.source_invoice_id)),
            func.min(ErpEntry.accounting_date),
            func.max(ErpEntry.accounting_date),
        ).where(ErpEntry.erp_account_id.in_(account_ids))
    ).one()
    entries, invoices, earliest, latest = row
    return {
        "entries": entries or 0,
        "invoices": invoices or 0,
        "earliest": earliest,
        "latest": latest,
    }
```

Then, in `replace_integration`, between the same-type 422 and the `try:` block:

```python
    if not body.confirm:
        history = _integration_history(session, outgoing)
        if history["entries"] or history["invoices"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=IntegrationReplaceBlocked(
                    detail=(
                        "This ERP has already posted to the ledger. Its data is "
                        "kept, and the new ERP will deliver overlapping periods "
                        "again as separate rows, so spend for those periods will "
                        "be counted twice. Send confirm=true to proceed."
                    ),
                    **history,
                ).model_dump(mode="json"),
            )
```

Add `IntegrationReplaceBlocked` to the `..schemas` import block.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/web_api/test_erp_integrations.py -q`
Expected: PASS, including Task 1's four.

Then the whole backend suite, because `_integration_history` is the first place these three tables are joined this way:
Run: `uv run pytest tests/web_api -q`
Expected: PASS.

- [ ] **Step 6: Document it in CLAUDE.md**

In the **ERP connectors** section, after the sentence beginning "An integration's `erp_type` is **fixed once connected**", add:

```markdown
  Moving a company to a different ERP is `POST /erp-integrations/{id}/replace`,
  which soft-disconnects the old integration and provisions the new one in **one
  transaction** — composed client-side, a failure between disconnect and create
  would leave the company connected to nothing. The old integration's accounts,
  entries and invoices are kept, which is why the endpoint **409s with the
  counts it would double** (entries, invoices, and the date span, joined through
  `ErpAccount` since neither `ErpEntry` nor `Invoice` names an integration)
  until `confirm=true`: the new ERP re-delivers overlapping periods as separate
  rows and no report can tell them apart. The same `erp_type` is a `422`
  pointing at `PATCH` — replacing would only retire the integration and restart
  its sync from scratch.
```

- [ ] **Step 7: Commit**

```bash
git add src/web_api/schemas.py src/web_api/routers/erp_integrations.py tests/web_api/test_erp_integrations.py CLAUDE.md
git commit -m "feat(api): confirm a replacement that would double the ledger"
```

---

### Task 3: Frontend client for `replace`

**Files:**
- Modify: `frontend/src/lib/types.ts` (add `ErpIntegrationReplace`, `ReplaceBlocked`)
- Modify: `frontend/src/lib/integrations.ts` (add `replaceIntegrationMutation`)
- Test: `frontend/src/lib/integrations.test.ts` (create if absent — check first)

**Interfaces:**
- Consumes: the Task 2 endpoint; `ApiClient.post<T>(path, body)` from `frontend/src/lib/api-client.ts`.
- Produces: `replaceIntegrationMutation(api, queryClient): UseMutationOptions<ErpIntegrationRead, Error, { id: string; body: ErpIntegrationReplace }>`. Task 5 calls `.mutateAsync`.

- [ ] **Step 1: Read how errors carry a body**

Read `frontend/src/lib/api-client.ts` and find how a non-2xx response becomes an `Error`. Task 5 must read `detail.invoices` off a 409, so note whether the thrown error exposes the parsed body (e.g. an `ApiError` with a `body`/`detail` property) or only a message string.

**If it only carries a message,** add a `body: unknown` property to the thrown error in `api-client.ts` and a test for it in that module's own test file. Do not parse the message string — a count recovered by regex from prose is a bug waiting for a copy edit.

- [ ] **Step 2: Write the failing test**

In `frontend/src/lib/integrations.test.ts`, matching the style of `frontend/src/lib/entries.test.ts` (read it for the `ApiClient` stub shape):

```ts
import { describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { replaceIntegrationMutation } from './integrations'
import type { ApiClient } from './api-client'

describe('replaceIntegrationMutation', () => {
  it('posts to the integration replace path', async () => {
    const post = vi.fn().mockResolvedValue({ id: 'new-1', erp_type: 'billy' })
    const api = { post } as unknown as ApiClient

    const options = replaceIntegrationMutation(api, new QueryClient())
    await options.mutationFn!({
      id: 'old-1',
      body: { erp_type: 'billy', label: 'Main', credentials: { access_token: 't' } },
    })

    expect(post).toHaveBeenCalledWith('/api/v1/erp-integrations/old-1/replace', {
      erp_type: 'billy',
      label: 'Main',
      credentials: { access_token: 't' },
    })
  })

  it('passes confirm through when the caller has acknowledged', async () => {
    const post = vi.fn().mockResolvedValue({ id: 'new-1' })
    const api = { post } as unknown as ApiClient

    const options = replaceIntegrationMutation(api, new QueryClient())
    await options.mutationFn!({
      id: 'old-1',
      body: { erp_type: 'billy', credentials: {}, confirm: true },
    })

    expect(post.mock.calls[0][1].confirm).toBe(true)
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && ./node_modules/.bin/vitest run src/lib/integrations.test.ts`
Expected: FAIL — `replaceIntegrationMutation` is not exported.

- [ ] **Step 4: Add the types**

In `frontend/src/lib/types.ts`, beside the other `ErpIntegration*` types:

```ts
/** Body of `POST /erp-integrations/{id}/replace`. Moves the company to a
 *  different ERP: the old integration is soft-disconnected, not deleted. */
export interface ErpIntegrationReplace {
  erp_type: string
  label?: string | null
  credentials: Record<string, string>
  /** Acknowledges that the old ERP's rows stay and the new one will re-deliver
   *  overlapping periods, so those periods are counted twice. */
  confirm?: boolean
}

/** The 409 body when a replacement would double already-posted spend. */
export interface ReplaceBlocked {
  detail: string
  invoices: number
  entries: number
  earliest: string | null
  latest: string | null
}
```

- [ ] **Step 5: Add the mutation**

In `frontend/src/lib/integrations.ts`, after `updateIntegrationMutation`:

```ts
/**
 * Move a company to a different ERP (`POST /erp-integrations/{id}/replace`).
 *
 * Not a variant of the update mutation: `PATCH` cannot change `erp_type`, and
 * this retires an integration. Without `confirm`, the API 409s with the counts
 * the switch would double — see `ReplaceBlocked`.
 */
export function replaceIntegrationMutation(
  api: ApiClient,
  queryClient: QueryClient,
): UseMutationOptions<
  ErpIntegrationRead,
  Error,
  { id: string; body: ErpIntegrationReplace }
> {
  return {
    mutationFn: ({ id, body }) =>
      api.post<ErpIntegrationRead>(`/api/v1/erp-integrations/${id}/replace`, body),
    onSuccess: () => invalidateIntegrations(queryClient),
  }
}
```

Add `ErpIntegrationReplace` to the `./types` import at the top of the file.

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd frontend && ./node_modules/.bin/vitest run src/lib/integrations.test.ts`
Expected: PASS, 2 tests.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/integrations.ts frontend/src/lib/integrations.test.ts
git commit -m "feat(frontend): client for replacing a company's ERP integration"
```

---

### Task 4: The live connector grid in edit mode

**Files:**
- Modify: `frontend/src/components/settings/companies-panel.tsx` (`ErpConnectionFields`, lines ~501-558)
- Test: `frontend/src/components/settings/companies-panel.test.tsx`

**Interfaces:**
- Consumes: `ErpTypeGrid({erpTypes, value, onSelect})` and `defaultCredentials(type)`, both already in this file.
- Produces: no new exports. The form's `erp_type` field now carries a value in edit mode, seeded to `integration.erp_type`; Task 5 reads it to decide PATCH vs replace.

**The change:** the edit branch currently renders a static `<p>` naming the connector. It renders `ErpTypeGrid` instead, and the fields below follow the selection — unchanged selection keeps today's label + `Replace credentials` form; a changed one shows the new connector's credential fields and hides the replace switch, since a new integration has nothing stored to replace.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/components/settings/companies-panel.test.tsx`. Read the existing edit-dialog tests first and reuse their render helper and fixtures rather than building new ones.

```tsx
it('shows the connector grid when editing, not a caption', async () => {
  renderPanel({ /* an existing company with a `mock` integration */ })
  await openEditDialog('Historied')

  expect(screen.getByRole('radiogroup', { name: 'ERP system' })).toBeInTheDocument()
  const chosen = screen.getByTestId('erp-type-mock').querySelector('input')
  expect(chosen).toBeChecked()
})

it('reveals the new connector fields when a different system is picked', async () => {
  renderPanel({ /* same */ })
  await openEditDialog('Historied')

  await userEvent.click(screen.getByTestId('erp-type-billy'))

  expect(screen.getByLabelText(/access token/i)).toBeInTheDocument()
  expect(
    screen.queryByLabelText(/replace credentials/i),
  ).not.toBeInTheDocument()
})

it('restores the replace-credentials form when the current system is reselected', async () => {
  renderPanel({ /* same */ })
  await openEditDialog('Historied')

  await userEvent.click(screen.getByTestId('erp-type-billy'))
  await userEvent.click(screen.getByTestId('erp-type-mock'))

  expect(screen.getByLabelText(/replace credentials/i)).toBeInTheDocument()
  expect(screen.queryByLabelText(/access token/i)).not.toBeInTheDocument()
})
```

The fixture needs **two** connectors in `erpTypes` (`mock` and `billy`) for the grid to be a choice. Check the file's existing `erpTypes` fixture and extend it if it has only one.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/settings/companies-panel.test.tsx -t 'connector grid'`
Expected: FAIL — no radiogroup in edit mode; the dialog renders the caption.

- [ ] **Step 3: Seed `erp_type` in edit mode**

In `CompanyDialog`'s `useForm` defaults (~line 691), change:

```tsx
      erp_type: preselected?.erp_type ?? '',
```

to:

```tsx
      // Seeded in edit mode too: the grid is live there now, and it must open
      // showing what is actually connected rather than nothing selected.
      erp_type: integration?.erp_type ?? preselected?.erp_type ?? '',
```

- [ ] **Step 4: Replace the static caption with the grid**

In `ErpConnectionFields`, replace the `mode === 'edit' && integration` block's static `<div>` (the `<p className="text-sm font-medium">ERP system</p>` block, ~lines 504-512) with nothing — the shared grid below now covers edit too — and change the grid's render condition from `mode === 'edit' ? null : (…)` to always render it.

Concretely, delete the static block, then change:

```tsx
          {mode === 'edit' ? null : (
            <FormField
              control={form.control}
              name="erp_type"
```

to:

```tsx
          <FormField
            control={form.control}
            name="erp_type"
```

closing the conditional accordingly, and add below the `<ErpTypeGrid …/>`'s `FormControl` a `FormDescription` shown only in edit mode:

```tsx
                  {mode === 'edit' ? (
                    <FormDescription>
                      Choosing a different system retires this connection and
                      starts a new one. Nothing already synced is deleted.
                    </FormDescription>
                  ) : null}
```

`FormDescription` is already imported in this file — confirm with `grep -n "FormDescription" frontend/src/components/settings/companies-panel.tsx`.

- [ ] **Step 5: Make the fields follow the selection**

At the top of `ErpConnectionFields`, after `const replacing = form.watch('replaceCredentials')`, add:

```tsx
  // In edit mode the grid is live, so "which connector's fields do we show" is
  // no longer the same question as "which one is connected".
  const switching = mode === 'edit' && !!selected && selected !== integration?.erp_type
```

Change `active` to follow the selection in every mode:

```tsx
  const active = erpTypes.find(
    (type) =>
      type.erp_type ===
      (mode === 'edit' && !switching ? integration?.erp_type : selected),
  )
```

Change `credentialFields` so a switch always asks for the new connector's fields:

```tsx
  // Editing without switching: nothing is stored to show, so the inputs appear
  // only once replacement is chosen. Switching: a new integration has no stored
  // credentials at all, so they are simply required.
  const credentialFields =
    !active ? [] : mode === 'edit' && !switching && !replacing ? [] : active.credential_fields
```

Wrap the `Replace credentials` switch block (the `<div className="flex flex-col gap-2">` containing it) in `{switching ? null : ( … )}` — replacing a secret that does not exist yet is not a choice worth painting.

- [ ] **Step 6: Reset the replace flag when switching starts**

In `ErpTypeGrid`'s `onSelect` handler inside the `erp_type` `FormField` (~line 578), after `field.onChange(next)` and the `setValue('credentials', …)` call, add:

```tsx
                        // A switch supplies fresh credentials by definition, so
                        // the edit-mode replace flag must not survive it and
                        // then leak into a PATCH if the user selects back.
                        form.setValue('replaceCredentials', false)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/settings/companies-panel.test.tsx`
Expected: PASS — the three new tests plus every existing one in the file. If an existing create-mode test breaks, the grid's render condition was changed too broadly; the `connect` and `create` behaviour must be untouched.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/settings/companies-panel.tsx frontend/src/components/settings/companies-panel.test.tsx
git commit -m "feat(frontend): the ERP grid is live when editing a company"
```

---

### Task 5: Submitting a switch, and confirming the one that would double spend

**Files:**
- Modify: `frontend/src/components/settings/companies-panel.tsx` (`CompaniesPanelProps`, `saveEdits`, a new confirm `AlertDialog`)
- Modify: `frontend/src/routes/_authed/settings/companies.index.tsx` (wire `onReplaceIntegration`)
- Test: `frontend/src/components/settings/companies-panel.test.tsx`

**Interfaces:**
- Consumes: `replaceIntegrationMutation` from Task 3; `switching`/`erp_type` form state from Task 4; the 409 body shape `ReplaceBlocked` from Task 2.
- Produces: `CompaniesPanelProps.onReplaceIntegration?: (id: string, values: {erp_type: string; label: string; credentials: Record<string, string>; confirm?: boolean}) => Promise<unknown>`.

- [ ] **Step 1: Write the failing tests**

```tsx
it('replaces the integration instead of patching it when the system changed', async () => {
  const onReplaceIntegration = vi.fn().mockResolvedValue({ id: 'new-1' })
  const onUpdateIntegration = vi.fn()
  renderPanel({ onReplaceIntegration, onUpdateIntegration })
  await openEditDialog('Historied')

  await userEvent.click(screen.getByTestId('erp-type-billy'))
  await userEvent.type(screen.getByLabelText(/access token/i), 'tok_live')
  await userEvent.click(screen.getByRole('button', { name: /save changes/i }))

  await waitFor(() =>
    expect(onReplaceIntegration).toHaveBeenCalledWith('int-1', {
      erp_type: 'billy',
      label: 'Main',
      credentials: { access_token: 'tok_live' },
    }),
  )
  expect(onUpdateIntegration).not.toHaveBeenCalled()
})

it('confirms a replacement the API says would double spend', async () => {
  const blocked = Object.assign(new Error('conflict'), {
    status: 409,
    body: {
      detail: {
        detail: 'This ERP has already posted to the ledger.',
        invoices: 25,
        entries: 989,
        earliest: '2026-01-05',
        latest: '2026-03-20',
      },
    },
  })
  const onReplaceIntegration = vi
    .fn()
    .mockRejectedValueOnce(blocked)
    .mockResolvedValueOnce({ id: 'new-1' })
  renderPanel({ onReplaceIntegration })
  await openEditDialog('Historied')

  await userEvent.click(screen.getByTestId('erp-type-billy'))
  await userEvent.type(screen.getByLabelText(/access token/i), 'tok_live')
  await userEvent.click(screen.getByRole('button', { name: /save changes/i }))

  expect(await screen.findByText(/989/)).toBeInTheDocument()
  expect(screen.getByText(/25 invoices/i)).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: /switch anyway/i }))

  await waitFor(() =>
    expect(onReplaceIntegration).toHaveBeenLastCalledWith(
      'int-1',
      expect.objectContaining({ confirm: true }),
    ),
  )
})
```

Match the error shape to what Task 3 Step 1 established for `ApiClient`. If the thrown error nests the body differently, use the real shape — do not adjust the client to fit this test.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/settings/companies-panel.test.tsx -t 'replace'`
Expected: FAIL — `onReplaceIntegration` is never called; `saveEdits` still routes everything through `onUpdateIntegration`.

- [ ] **Step 3: Add the prop**

In `CompaniesPanelProps`, after `onUpdateIntegration`:

```tsx
  /**
   * Move a company to a different ERP. Distinct from `onUpdateIntegration`
   * because `PATCH` cannot change `erp_type`: this retires the old integration
   * and starts a new one. Rejects with a 409 carrying the counts it would
   * double until `confirm` is set.
   */
  onReplaceIntegration?: (
    id: string,
    values: {
      erp_type: string
      label: string
      credentials: Record<string, string>
      confirm?: boolean
    },
  ) => Promise<unknown>
```

Destructure it in the `CompaniesPanel({ … })` parameter list alongside `onUpdateIntegration`.

- [ ] **Step 4: Branch `saveEdits` on the connector having changed**

In `saveEdits` (~line 952), replace the `if (integration) { … }` branch's opening with:

```tsx
    if (integration && values.erp_type && values.erp_type !== integration.erp_type) {
      // The system itself changed, so this is a replacement, not an edit — the
      // API refuses `erp_type` on a PATCH, and the two are different actions.
      await replaceIntegration(integration.id, {
        erp_type: values.erp_type,
        label: values.label,
        credentials,
      })
    } else if (integration) {
```

and add above `saveEdits`, in the component body, the state and the caller:

```tsx
  const [blocked, setBlocked] = React.useState<{
    integrationId: string
    values: { erp_type: string; label: string; credentials: Record<string, string> }
    counts: ReplaceBlocked
  } | null>(null)

  /** Post the replacement, surfacing a 409 as the confirm dialog rather than
   *  as an error — the counts are the whole point of the refusal. */
  async function replaceIntegration(
    integrationId: string,
    values: { erp_type: string; label: string; credentials: Record<string, string> },
    confirm = false,
  ) {
    try {
      await onReplaceIntegration?.(integrationId, { ...values, ...(confirm ? { confirm } : {}) })
      setBlocked(null)
    } catch (err) {
      const counts = replaceBlockedFrom(err)
      if (!counts) throw err
      setBlocked({ integrationId, values, counts })
    }
  }
```

Add the narrowing helper near `changedFields` at module scope:

```tsx
/** The 409 body of a blocked replacement, or null for any other failure.
 *
 * Read off the error's parsed body rather than its message: a count recovered
 * from prose would break on a copy edit.
 */
export function replaceBlockedFrom(err: unknown): ReplaceBlocked | null {
  const body = (err as { body?: { detail?: unknown } } | null)?.body?.detail
  if (!body || typeof body !== 'object') return null
  const detail = body as Partial<ReplaceBlocked>
  return typeof detail.entries === 'number' && typeof detail.invoices === 'number'
    ? (detail as ReplaceBlocked)
    : null
}
```

Import `ReplaceBlocked` from `@/lib/types`.

- [ ] **Step 5: Add the confirm dialog**

Beside the existing `reassigned` `AlertDialog` (~line 1240), which this deliberately mirrors:

```tsx
      <AlertDialog
        open={blocked !== null}
        onOpenChange={(open) => !open && setBlocked(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Switch ERP anyway?</AlertDialogTitle>
            <AlertDialogDescription>
              The current connection has posted {blocked?.counts.entries} entries
              across {blocked?.counts.invoices} invoices
              {blocked?.counts.earliest && blocked?.counts.latest
                ? `, from ${blocked.counts.earliest} to ${blocked.counts.latest}`
                : ''}
              . None of it is deleted — but the new system will deliver those
              periods again as separate rows, so spend covering them will be
              counted twice in reports.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button variant="ghost" onClick={() => setBlocked(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() =>
                blocked &&
                void replaceIntegration(blocked.integrationId, blocked.values, true)
              }
            >
              Switch anyway
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
```

- [ ] **Step 6: Wire the route**

In `frontend/src/routes/_authed/settings/companies.index.tsx`, add the mutation beside `updateIntegration`:

```tsx
  const replaceIntegration = useMutation(replaceIntegrationMutation(api, queryClient))
```

and the prop beside `onUpdateIntegration`:

```tsx
      onReplaceIntegration={(id, values) =>
        replaceIntegration.mutateAsync({
          id,
          body: {
            erp_type: values.erp_type,
            label: values.label || null,
            credentials: values.credentials,
            ...(values.confirm ? { confirm: true } : {}),
          },
        })
      }
```

Import `replaceIntegrationMutation` from `@/lib/integrations`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/settings/companies-panel.test.tsx`
Expected: PASS.

Then everything, since `saveEdits` and the panel props changed:
Run: `cd frontend && ./node_modules/.bin/vitest run`
Expected: PASS.

Then typecheck:
Run: `cd frontend && ./node_modules/.bin/tsc --noEmit`
Expected: no errors.

- [ ] **Step 8: Document the dialog in CLAUDE.md**

In the **Web API roles & endpoints** section, add `/erp-integrations/{id}/replace` to the list of integration actions alongside `disconnect|reconnect|test-connection|refresh-accounts`, noting it is management-gated and 409s without `confirm`.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/settings/companies-panel.tsx \
        frontend/src/components/settings/companies-panel.test.tsx \
        frontend/src/routes/_authed/settings/companies.index.tsx CLAUDE.md
git commit -m "feat(frontend): switch a company's ERP from the edit dialog"
```

---

## Final verification

- [ ] `uv run pytest -q` — full backend suite passes (834 tests before this work).
- [ ] `cd frontend && ./node_modules/.bin/vitest run` — full frontend suite passes.
- [ ] `cd frontend && ./node_modules/.bin/tsc --noEmit` — clean.
- [ ] Manual: open Settings → Companies → edit a company. The grid renders with the connected system selected. Picking another reveals its fields; saving with ledger history shows the confirm dialog with real counts; confirming leaves the old integration listed as disconnected and the new one live.
