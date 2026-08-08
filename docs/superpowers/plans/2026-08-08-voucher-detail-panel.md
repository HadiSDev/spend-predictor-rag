# Voucher Detail Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the entry-scoped read-only `EntryDrawer` with a URL-addressable, voucher-scoped panel showing the invoice PDF, correctable AI fields, the voucher's ERP postings, and a voucher-wide audit feed.

**Architecture:** Provenance decides affordance — AI-produced values are inputs, ERP-posted values are flat evidence — enforced by a new `Invoice.source` column rather than by convention. Real PDF bytes flow mock_erp → connector → web API → browser, with no storage layer introduced. Panel state lives in the `/entries` route's search params so a shared link reopens the same panel over the same filtered list.

**Tech Stack:** Python 3.12 + FastAPI + SQLModel + Alembic + WeasyPrint/Jinja2; React 19 + TanStack Router/Query + Base UI + Tailwind 4 + react-pdf; pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-08-08-voucher-detail-panel-design.md`

## Global Constraints

- Python is managed with `uv`; run tests as `uv run pytest`, never bare `pytest`.
- The frontend uses **bun**. `bun.lock` is committed. Never run `pnpm`/`npm` here.
- **Do not run package-manager installs.** Task 11 requires `bun add react-pdf`; stop and ask the user to run it. Call binaries directly as `./node_modules/.bin/vitest`.
- `web_api` **never** imports `ai_api`. The dependency runs one way only.
- ERP as-posted columns are never rewritten. Only AI-produced values are writable.
- Alembic chain head in the working tree is `0017_entry_source_line` (currently **untracked** in git — confirm with `git status` before writing a migration and chain from whatever is actually head).
- Infra ports: Postgres 5433, mock ERP/vLLM 8001 — 5432/8000 are taken by other projects.
- The user runs dev servers themselves. Hand over commands; do not launch them.

## Spec corrections discovered during planning

Both were verified against the code and supersede the spec where they conflict:

1. **`VoucherGroupRead.entries` already exists** (`schemas.py:309`), so `GET /erp-entries/vouchers` already returns every posting of every voucher. `VoucherDetailRead` is therefore needed only for cold deep-link loads and for the invoice/lines/document — not to re-deliver postings the panel already has.
2. **`_connector_config` lives in `ai_api/sync/runner.py:139`**, which `web_api` cannot import. Task 4 lifts it into `web_api/integrations.py` as a shared helper instead of duplicating it.

---

## File Structure

**Backend — create:**
- `mock_erp/documents.py` — renders one invoice dict to PDF bytes
- `mock_erp/templates/invoice.html` — the Jinja2 invoice template
- `src/web_api/db/migrations/versions/0018_invoice_source.py`
- `tests/web_api/test_voucher_detail.py`
- `tests/web_api/test_invoice_document.py`

**Backend — modify:**
- `src/web_api/db/models/invoice.py` — add `source`
- `src/web_api/connectors/base.py` — `DocumentPayload`, `fetch_invoice_document`
- `src/web_api/connectors/mock.py` — implement it
- `src/web_api/integrations.py` — `connector_config`, `connector_for_integration`
- `src/web_api/schemas.py` — `VoucherDetailRead`, `VoucherAuditRead`, `InvoiceUpdate`, `InvoiceRead` additions
- `src/web_api/routers/invoices.py` — document route, `PATCH`
- `src/web_api/routers/erp_entries.py` — voucher detail + audit routes
- `src/web_api/audit.py` — `INVOICE_AUDIT_FIELDS`
- `mock_erp/main.py` — document route
- `tests/test_mock_erp.py`, `tests/web_api/conftest.py`

**Frontend — create:** `voucher-drawer.tsx`, `invoice-document.tsx`, `voucher-details-tab.tsx`, `voucher-postings-tab.tsx`, `voucher-activity-tab.tsx`, `line-category-editor.tsx` (all in `frontend/src/components/entries/`), plus `voucher-drawer.test.tsx`.

**Frontend — modify:** `ui/drawer.tsx`, `lib/api-client.ts`, `lib/entries.ts`, `lib/types.ts`, `lib/entry-search.ts`, `components/entries/entries-panel.tsx`, `routes/_authed/entries.tsx`. **Delete:** `components/entries/entry-drawer.tsx` (its `ConversionRows` moves to `voucher-postings-tab.tsx` intact).

---

### Task 1: `Invoice.source` provenance column

**Files:**
- Modify: `src/web_api/db/models/invoice.py:24`
- Modify: `src/web_api/schemas.py` (`InvoiceRead`)
- Create: `src/web_api/db/migrations/versions/0018_invoice_source.py`
- Test: `tests/web_api/test_invoices.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Invoice.source: str` (`'erp' | 'pdf_extraction'`, NOT NULL, default `'erp'`), exposed as `InvoiceRead.source`.

- [ ] **Step 1: Write the failing test**

In `tests/web_api/test_invoices.py`:

```python
def test_invoice_read_exposes_erp_provenance_by_default(client, seed):
    res = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA"))
    assert res.status_code == 200
    # Sync-created invoices are ERP evidence: their header is not correctable.
    assert res.json()["source"] == "erp"
```

Ensure the file imports `auth` from `.conftest` as the sibling tests do.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web_api/test_invoices.py::test_invoice_read_exposes_erp_provenance_by_default -v`
Expected: FAIL — `KeyError: 'source'`.

- [ ] **Step 3: Add the column to the model**

In `src/web_api/db/models/invoice.py`, after the `status` field:

```python
    # Provenance, which decides what may be corrected. 'erp' rows are as-posted
    # evidence and their header is read-only; 'pdf_extraction' rows came from the
    # AI's parse of a document and may be corrected by a human.
    source: str = Field(sa_type=String, nullable=False, default="erp")
```

- [ ] **Step 4: Expose it on the schema**

In `src/web_api/schemas.py`, in `InvoiceRead`, after `status`:

```python
    # 'erp' | 'pdf_extraction' — see Invoice.source.
    source: str = "erp"
```

- [ ] **Step 5: Write the migration**

Create `src/web_api/db/migrations/versions/0018_invoice_source.py`:

```python
"""Record where an invoice's values came from

Revision ID: 0018_invoice_source
Revises: 0017_entry_source_line
Create Date: 2026-08-08

Adds ``invoices.source`` — 'erp' or 'pdf_extraction'.

Corrections apply only to what the AI produced. Without a provenance marker that
rule is a convention the UI remembers; with one it is a condition the API can
enforce, which is what keeps the as-posted ERP columns evidence.

Existing rows are all sync-created, so they backfill to 'erp'. Reversible:
downgrade drops the column.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0018_invoice_source"
down_revision = "0017_entry_source_line"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("source", sa.String(), nullable=False, server_default="erp"),
    )


def downgrade() -> None:
    op.drop_column("invoices", "source")
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/web_api/test_invoices.py -v`
Expected: PASS.

- [ ] **Step 7: Verify the migration applies and reverses**

Run: `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: three clean runs, no error. If Postgres is not running, note it and move on — the SQLite test suite already covers the column.

- [ ] **Step 8: Commit**

```bash
git add src/web_api/db/models/invoice.py src/web_api/schemas.py \
        src/web_api/db/migrations/versions/0018_invoice_source.py \
        tests/web_api/test_invoices.py
git commit -m "feat(web_api): record invoice provenance so corrections can be gated"
```

---

### Task 2: mock_erp renders real invoice PDFs

**Files:**
- Create: `mock_erp/documents.py`, `mock_erp/templates/invoice.html`
- Modify: `mock_erp/main.py`
- Test: `tests/test_mock_erp.py`

**Interfaces:**
- Consumes: the invoice dicts from `mock_erp/data/invoices.py` (keys: `purchaseInvoiceNumber`, `voucherId`, `file`, `supplier`, `date`, `currency`, `grossAmount`, `netAmount`, `vatAmount`, `lines`).
- Produces: `render_invoice_pdf(invoice: dict) -> bytes`; route `GET /api/v1/documents/{voucher_id}` returning `application/pdf`.

- [ ] **Step 1: Write the failing test**

In `tests/test_mock_erp.py`:

```python
def test_document_route_returns_a_pdf_for_a_voucher_with_an_invoice(client):
    invoices = client.get("/api/v1/purchase-invoices").json()["collection"]
    voucher_id = invoices[0]["voucherId"]

    res = client.get(f"/api/v1/documents/{voucher_id}")

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    # A real PDF, not an error page rendered with the wrong content type.
    assert res.content.startswith(b"%PDF-")


def test_document_route_404s_for_a_voucher_with_no_invoice(client):
    res = client.get("/api/v1/documents/99999999")
    assert res.status_code == 404
```

Match the existing fixture style in that file; reuse its `client` fixture.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mock_erp.py -k document -v`
Expected: FAIL with 404 on both (route does not exist).

- [ ] **Step 3: Write the invoice template**

Create `mock_erp/templates/invoice.html`:

```html
<!doctype html>
<meta charset="utf-8">
<style>
  @page { size: A4; margin: 18mm; }
  body { font-family: "DejaVu Sans", sans-serif; font-size: 10pt; color: #111; }
  h1 { font-size: 16pt; margin: 0 0 2mm; }
  .muted { color: #666; }
  .meta { display: flex; justify-content: space-between; margin: 8mm 0 6mm; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; border-bottom: 1px solid #333; padding: 2mm 0; }
  td { padding: 2mm 0; border-bottom: 1px solid #eee; }
  .num { text-align: right; }
  .totals { margin-top: 6mm; margin-left: auto; width: 60mm; }
  .totals div { display: flex; justify-content: space-between; padding: 1mm 0; }
  .grand { border-top: 1px solid #333; font-weight: bold; }
</style>
<h1>{{ supplier.name }}</h1>
<div class="muted">Supplier no. {{ supplier.supplierNumber }}</div>
<div class="meta">
  <div><strong>Invoice {{ invoice_number }}</strong><br>
       <span class="muted">Voucher {{ voucher_id }}</span></div>
  <div>{{ date }}</div>
</div>
<table>
  <thead>
    <tr><th>Description</th><th class="num">Qty</th>
        <th class="num">Unit</th><th class="num">Net</th></tr>
  </thead>
  <tbody>
    {% for line in lines %}
    <tr>
      <td>{{ line.description }}</td>
      <td class="num">{{ line.quantity }}</td>
      <td class="num">{{ '%.2f'|format(line.unitPrice) }}</td>
      <td class="num">{{ '%.2f'|format(line.netAmount) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<div class="totals">
  <div><span>Net</span><span>{{ '%.2f'|format(net) }}</span></div>
  <div><span>VAT</span><span>{{ '%.2f'|format(vat) }}</span></div>
  <div class="grand"><span>Total {{ currency }}</span><span>{{ '%.2f'|format(gross) }}</span></div>
</div>
```

- [ ] **Step 4: Write the renderer**

Create `mock_erp/documents.py`:

```python
"""Render a generated purchase invoice to PDF bytes.

The document is rendered from the *same* dict the invoice endpoints serve, so
the scan a reviewer reads always agrees with the rows that were synced from it.
A document that disagreed with its data would make the correction UI untestable.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_invoice_pdf(invoice: dict) -> bytes:
    """Render one invoice dict to PDF bytes."""
    # Local import: WeasyPrint pulls in heavy native deps, and importing this
    # module must stay cheap for callers that never render. Mirrors
    # ai_api/synthdata/render/renderer.py.
    from weasyprint import HTML

    html = _env.get_template("invoice.html").render(
        supplier=invoice["supplier"],
        invoice_number=invoice["purchaseInvoiceNumber"],
        voucher_id=invoice["voucherId"],
        date=invoice["date"],
        currency=invoice["currency"],
        lines=invoice.get("lines", []),
        net=invoice["netAmount"],
        vat=invoice["vatAmount"],
        gross=invoice["grossAmount"],
    )
    return HTML(string=html).write_pdf()


def render_for_voucher(invoice: dict) -> bytes:
    """Render with a per-voucher memo. Rendering costs ~100ms and the data is
    static between regenerations, so the same voucher is only ever rendered once.
    """
    key = str(invoice["voucherId"])
    if key not in _MEMO:
        _MEMO[key] = render_invoice_pdf(invoice)
    return _MEMO[key]


_MEMO: dict[str, bytes] = {}


def clear_cache() -> None:
    """Drop memoized documents. Called when the mock regenerates its data."""
    _MEMO.clear()
```

Delete the unused `_render_cached` stub before committing — it is shown here only to be explicitly removed; the `_MEMO` dict is the real mechanism.

- [ ] **Step 5: Add the route**

In `mock_erp/main.py`, import at the top:

```python
from fastapi.responses import JSONResponse, Response

from .documents import clear_cache, render_for_voucher
```

Add `clear_cache()` as the first statement inside `regenerate_data()`, so regenerated data never serves a stale document.

Add the route after the purchase-invoice routes:

```python
# ── Documents ───────────────────────────────────────────────────────────────


@app.get("/api/v1/documents/{voucher_id}")
async def get_document(voucher_id: str) -> Response:
    """The scanned invoice for a voucher, as a PDF.

    Vouchers that are not purchase invoices (payments, journal entries) have no
    document and 404 — the same distinction `fetch_invoice_scan` already makes.
    """
    match = next(
        (inv for inv in _INVOICES if str(inv.get("voucherId")) == str(voucher_id)),
        None,
    )
    if match is None:
        raise HTTPException(status_code=404, detail="No document for this voucher")
    filename = match.get("file", {}).get("fileName", f"voucher_{voucher_id}.pdf")
    return Response(
        content=render_for_voucher(match),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_mock_erp.py -k document -v`
Expected: PASS. If WeasyPrint raises a missing-native-library error (pango/cairo), report it to the user rather than working around it — it is an environment problem, not a code one.

- [ ] **Step 7: Run the whole mock ERP suite for regressions**

Run: `uv run pytest tests/test_mock_erp.py -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add mock_erp/documents.py mock_erp/templates/invoice.html mock_erp/main.py tests/test_mock_erp.py
git commit -m "feat(mock_erp): serve real invoice PDFs rendered from the synced data"
```

---

### Task 3: Connector document fetch

**Files:**
- Modify: `src/web_api/connectors/base.py`, `src/web_api/connectors/mock.py`
- Test: `tests/test_connectors.py` (create if absent)

**Interfaces:**
- Consumes: mock ERP `GET /api/v1/documents/{voucher_id}` from Task 2.
- Produces: `DocumentPayload(content: bytes, media_type: str, filename: str)` and abstract `ErpConnector.fetch_invoice_document(voucher_id: str) -> DocumentPayload | None`.

- [ ] **Step 1: Write the failing test**

In `tests/test_connectors.py`:

```python
import pytest

from web_api.connectors.mock import MockErpConnector


@pytest.fixture
def connector(mock_erp_base_url):
    return MockErpConnector({"base_url": mock_erp_base_url})


def test_fetch_invoice_document_returns_pdf_bytes(connector):
    invoices = connector.fetch_invoices()
    voucher_id = invoices[0].voucher_id

    payload = connector.fetch_invoice_document(voucher_id)

    assert payload is not None
    assert payload.media_type == "application/pdf"
    assert payload.content.startswith(b"%PDF-")
    assert payload.filename.endswith(".pdf")


def test_fetch_invoice_document_returns_none_for_a_voucher_with_no_scan(connector):
    # Distinct from a failed fetch, which raises: None means "nothing attached".
    assert connector.fetch_invoice_document("99999999") is None
```

`mock_erp_base_url` must point at a running mock ERP. If the existing suite has no such fixture, add one to `tests/conftest.py` that spins the mock app up in-process:

```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_erp_base_url(monkeypatch):
    """Serve the mock ERP in-process and route connector HTTP calls to it."""
    from mock_erp.main import app, regenerate_data
    import httpx

    regenerate_data()
    transport = httpx.ASGITransport(app=app)
    real_client = httpx.Client

    def _client(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _client)
    return "http://mock-erp"
```

Confirm the connector's actual HTTP mechanism first (`grep -n "httpx\|requests" src/web_api/connectors/mock.py`) and adapt the fixture to it — if it uses `requests`, patch that instead.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_connectors.py -v`
Expected: FAIL — `AttributeError: 'MockErpConnector' object has no attribute 'fetch_invoice_document'`.

- [ ] **Step 3: Declare the payload and the abstract method**

In `src/web_api/connectors/base.py`, beside the other data models:

```python
class DocumentPayload(BaseModel):
    """A fetched document's bytes and how to serve them."""

    content: bytes
    media_type: str = "application/pdf"
    filename: str
```

And on `ErpConnector`, directly after `fetch_invoice_scan`:

```python
    @abstractmethod
    def fetch_invoice_document(self, voucher_id: str) -> DocumentPayload | None:
        """The scanned document attached to a voucher, or ``None`` if it has none.

        Keyed by voucher, exactly like ``fetch_invoice_scan`` — the document and
        the scan record are two views of one thing.

        ``None`` means "nothing is attached", which is the ordinary case for a
        payment or a journal entry. A fetch that *failed* must raise
        ``ErpConnectionError`` instead, so a caller can tell a missing document
        from an unreachable ERP.
        """
```

- [ ] **Step 4: Implement it on the mock connector**

In `src/web_api/connectors/mock.py`, after `fetch_invoice_scan`:

```python
    def fetch_invoice_document(self, voucher_id: str) -> DocumentPayload | None:
        """Fetch the voucher's PDF from the mock ERP's document endpoint."""
        response = self._request_raw(f"/api/v1/documents/{voucher_id}")
        if response is None:
            return None
        content, filename = response
        return DocumentPayload(
            content=content,
            media_type="application/pdf",
            filename=filename or f"voucher_{voucher_id}.pdf",
        )
```

Add `_request_raw` beside the existing `_paginate`/request helpers, mirroring their auth, timeout and error handling. It must return `None` on 404 and raise `ErpConnectionError` on transport failure or any other non-2xx, and extract the filename from `Content-Disposition` when present. Import `DocumentPayload` from `.base`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_connectors.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite — the new abstract method breaks any other connector**

Run: `uv run pytest -x -q`
Expected: PASS. `fetch_invoice_document` is abstract, so any connector subclass missing it fails at instantiation. `mock` is the only registered connector, but test fakes may also subclass `ErpConnector` — give each one the method returning `None`.

- [ ] **Step 7: Commit**

```bash
git add src/web_api/connectors/base.py src/web_api/connectors/mock.py tests/test_connectors.py tests/conftest.py
git commit -m "feat(connectors): fetch a voucher's attached document"
```

---

### Task 4: `GET /invoices/{id}/document`

**Files:**
- Modify: `src/web_api/integrations.py`, `src/web_api/routers/invoices.py`, `src/web_api/schemas.py`
- Test: `tests/web_api/test_invoice_document.py`

**Interfaces:**
- Consumes: `DocumentPayload`, `fetch_invoice_document` (Task 3); `decrypt_config` from `web_api.credentials`; `get_connector` from `web_api.connectors`.
- Produces: `connector_config(session, integration) -> dict`, `connector_for_integration(session, integration) -> ErpConnector` in `web_api/integrations.py`; route `GET /api/v1/invoices/{invoice_id}/document`; `InvoiceRead.file_id`, `.file_name`, `.has_document`.

- [ ] **Step 1: Write the failing tests**

Create `tests/web_api/test_invoice_document.py`:

```python
from .conftest import auth


def test_document_404s_when_no_file_is_attached(client, seed):
    # The seeded invoices have no File row, so there is nothing to serve.
    res = client.get(f"/api/v1/invoices/{seed['inv_a']}/document", headers=auth("tokA"))
    assert res.status_code == 404


def test_document_is_tenant_scoped(client, seed):
    # Org B's invoice must be indistinguishable from one that does not exist.
    res = client.get(f"/api/v1/invoices/{seed['inv_b']}/document", headers=auth("tokA"))
    assert res.status_code == 404


def test_invoice_read_reports_whether_a_document_exists(client, seed):
    body = client.get(f"/api/v1/invoices/{seed['inv_a']}", headers=auth("tokA")).json()
    assert body["has_document"] is False
    assert body["file_id"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/web_api/test_invoice_document.py -v`
Expected: FAIL — 404 route missing gives 404 for the wrong reason on the first two, and `KeyError: 'has_document'` on the third. Make the third pass first so the failures are unambiguous.

- [ ] **Step 3: Extend `InvoiceRead`**

In `src/web_api/schemas.py`, in `InvoiceRead` after `source`:

```python
    file_id: str | None = None
    # Resolved from the linked File so a client never needs a second lookup to
    # decide whether to render a viewer.
    file_name: str | None = None
    has_document: bool = False
```

Populate `file_name`/`has_document` in the invoice routes by building the payload from the ORM row plus its `file` relationship, as `get_invoice` already does with `model_dump()`.

- [ ] **Step 4: Lift the connector helpers into `web_api`**

In `src/web_api/integrations.py`:

```python
def connector_config(session: Session, integration: ErpIntegration) -> dict:
    """The integration's decrypted credentials, or ``{}`` for connector defaults.

    No credential row is the normal case for a connector whose fields all have
    defaults (the Debug ERP is one), so it is not an error.
    """
    credential = session.exec(
        select(ErpCredential).where(ErpCredential.erp_integration_id == integration.id)
    ).first()
    if credential is None:
        return {}
    try:
        return decrypt_config(credential.encrypted_config)
    except Exception as exc:
        raise RuntimeError(
            f"Could not decrypt credentials for integration {integration.id} — "
            "is WEB_API_CREDENTIAL_ENC_KEY set to the key they were written with?"
        ) from exc


def connector_for_integration(session: Session, integration: ErpIntegration) -> ErpConnector:
    """A configured connector for this integration."""
    return get_connector(integration.erp_type, connector_config(session, integration))
```

Then change `ai_api/sync/runner.py:_connector_config` to delegate: `from web_api.integrations import connector_config` and have the runner call it. `ai_api` importing `web_api` is the correct direction; do not move it the other way.

- [ ] **Step 5: Add the document route**

In `src/web_api/routers/invoices.py`:

```python
@router.get("/invoices/{invoice_id}/document")
def get_invoice_document(
    invoice_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Response:
    """Stream the invoice's scanned document, fetched live from the ERP.

    Not stored locally: the document lives in the ERP, and copying it here would
    create a second source of truth to keep in sync. The trade-off is that this
    hits the ERP on every open — the first place to add a cache if it hurts.
    """
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.company_id not in scope.company_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if invoice.file_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No document attached to this invoice"
        )

    integration, voucher_id = _resolve_document_source(session, invoice)
    connector = connector_for_integration(session, integration)
    try:
        payload = connector.fetch_invoice_document(voucher_id)
    except ErpConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach the ERP to fetch this document: {exc}",
        ) from exc
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="The ERP has no document for this voucher"
        )
    return Response(
        content=payload.content,
        media_type=payload.media_type,
        headers={"Content-Disposition": f'inline; filename="{payload.filename}"'},
    )
```

And the resolver above it:

```python
def _resolve_document_source(session: Session, invoice: Invoice) -> tuple[ErpIntegration, str]:
    """Which integration holds this invoice's document, and under which voucher.

    An invoice carries no integration id. The only path is through its postings:
    entry -> erp_account -> erp_integration, constrained at every hop to the
    invoice's own company. When that does not yield a *connected* integration and
    a real voucher id, we refuse rather than guess.

    There is deliberately no fallback. An earlier draft fell back to the
    company's single connected integration keyed by `invoice_number`, which is
    the *supplier's* number while voucher ids are the ERP's own sequence — two
    namespaces, so a numeric supplier number can collide with a real voucher and
    serve a document belonging to a different transaction.
    """
    row = session.exec(
        select(ErpEntry, ErpAccount)
        .join(ErpAccount, ErpAccount.id == ErpEntry.erp_account_id)
        .where(
            ErpEntry.source_invoice_id == invoice.id,
            # Never leave the invoice's tenant: a mis-synced entry pointing at
            # another company's account would otherwise have this endpoint
            # decrypt that tenant's credentials and query their ERP.
            ErpEntry.company_id == invoice.company_id,
            ErpEntry.voucher_id.is_not(None),
        )
        .order_by(ErpEntry.id)
    ).first()
    if row is not None:
        entry, account = row
        integration = session.get(ErpIntegration, account.erp_integration_id)
        if (
            integration is not None
            and integration.disconnected_at is None
            and integration.company_id == invoice.company_id
        ):
            return integration, str(entry.voucher_id)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Cannot determine which ERP holds this document",
    )
```

Add the imports this needs: `Response` from `fastapi`, `ErpAccount`/`ErpEntry`/`ErpIntegration` from `web_api.db.models`, `ErpConnectionError` from `web_api.connectors.base`, `connector_for_integration` from `..integrations`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/web_api/test_invoice_document.py -v`
Expected: PASS.

- [ ] **Step 7: Add a 502 test with a failing connector**

```python
def test_document_502s_when_the_erp_is_unreachable(client, seed, monkeypatch):
    """A dead ERP must be reported as such, never as a missing document — the UI
    offers retry for one and a different message for the other."""
    from web_api import integrations
    from web_api.connectors.base import ErpConnectionError

    class DeadConnector:
        def fetch_invoice_document(self, voucher_id):
            raise ErpConnectionError("connection refused")

    monkeypatch.setattr(integrations, "connector_for_integration", lambda *a: DeadConnector())
    # Seed a File + ErpEntry + ErpAccount + ErpIntegration for inv_a first; see
    # the voucher fixture added in Task 5 and reuse it here.
```

Complete this test using the `voucher_seed` fixture from Task 5 — if you are doing Task 4 before Task 5, write that fixture now in `tests/web_api/conftest.py` and reference it from both.

- [ ] **Step 8: Run the full backend suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/web_api/integrations.py src/web_api/routers/invoices.py src/web_api/schemas.py \
        src/ai_api/sync/runner.py tests/web_api/test_invoice_document.py tests/web_api/conftest.py
git commit -m "feat(web_api): stream an invoice's ERP document, tenant-scoped"
```

---

### Task 5: Voucher detail endpoint

**Files:**
- Modify: `src/web_api/routers/erp_entries.py`, `src/web_api/schemas.py`, `tests/web_api/conftest.py`
- Test: `tests/web_api/test_voucher_detail.py`

**Interfaces:**
- Consumes: `_entry_select()`, `_entry_read()`, `_entry_conditions()` in `erp_entries.py`; `InvoiceDetailRead`.
- Produces: `VoucherDetailRead`; routes `GET /api/v1/erp-entries/vouchers/{voucher_id}` and `GET /api/v1/erp-entries/vouchers/by-entry/{entry_id}`.

- [ ] **Step 1: Add a voucher fixture to `tests/web_api/conftest.py`**

```python
@pytest.fixture
def voucher_seed(engine, seed):
    """Org A gains a real voucher: an integration, an account, a File-backed
    invoice, and three postings — one of them a payment, so the exclusion rule
    can be tested."""
    from web_api.db.models import ErpAccount, ErpEntry, ErpIntegration, File

    with Session(engine) as s:
        integ = ErpIntegration(company_id=seed["comp_a"], erp_type="mock", label="Main")
        s.add(integ)
        s.commit()
        acct = ErpAccount(company_id=seed["comp_a"], erp_integration_id=integ.id,
                          account_code="6200", name="Software", account_type="expense")
        s.add(acct)
        f = File(company_id=seed["comp_a"], filename="invoice_4821.pdf",
                 file_type="invoice_pdf", storage_path="scans/4821/invoice_4821.pdf")
        s.add(f)
        s.commit()
        inv = s.get(Invoice, seed["inv_a"])
        inv.file_id = f.id
        s.add(inv)
        entries = [
            ErpEntry(company_id=seed["comp_a"], erp_account_id=acct.id,
                     source_invoice_id=inv.id, voucher_id="4821",
                     entry_type="purchase_invoice", accounting_date=date(2025, 7, 1),
                     debit_amount=Decimal("100.00"), currency="DKK"),
            ErpEntry(company_id=seed["comp_a"], erp_account_id=acct.id,
                     source_invoice_id=inv.id, voucher_id="4821",
                     entry_type="payment", accounting_date=date(2025, 7, 1),
                     credit_amount=Decimal("100.00"), currency="DKK"),
            # A lone posting with no voucher — the by-entry case.
            ErpEntry(company_id=seed["comp_a"], erp_account_id=acct.id,
                     voucher_id=None, entry_type="journal_entry",
                     accounting_date=date(2025, 7, 2),
                     debit_amount=Decimal("5.00"), currency="DKK"),
        ]
        for e in entries:
            s.add(e)
        s.commit()
        return {**seed, "integration": integ.id, "account": acct.id, "file": f.id,
                "voucher": "4821", "lone_entry": entries[2].id}
```

Adjust field names to the real model signatures if they differ — check `ErpAccount` and `ErpIntegration` before writing.

- [ ] **Step 2: Write the failing tests**

Create `tests/web_api/test_voucher_detail.py`:

```python
from .conftest import auth


def test_voucher_detail_returns_postings_invoice_and_document(client, voucher_seed):
    res = client.get(f"/api/v1/erp-entries/vouchers/{voucher_seed['voucher']}",
                     headers=auth("tokA"))

    assert res.status_code == 200
    body = res.json()
    assert body["voucher_id"] == "4821"
    assert body["invoice"]["id"] == voucher_seed["inv_a"]
    assert len(body["invoice"]["lines"]) == 2
    assert body["document"]["filename"] == "invoice_4821.pdf"


def test_voucher_detail_includes_payment_postings(client, voucher_seed):
    """A voucher the user navigated to is a lookup, not a listing — hiding a
    posting would make the voucher's own totals unexplainable."""
    body = client.get(f"/api/v1/erp-entries/vouchers/{voucher_seed['voucher']}",
                      headers=auth("tokA")).json()

    assert {e["entry_type"] for e in body["entries"]} == {"purchase_invoice", "payment"}


def test_by_entry_resolves_a_posting_with_no_voucher(client, voucher_seed):
    res = client.get(
        f"/api/v1/erp-entries/vouchers/by-entry/{voucher_seed['lone_entry']}",
        headers=auth("tokA"),
    )

    assert res.status_code == 200
    body = res.json()
    assert body["voucher_id"] is None
    assert len(body["entries"]) == 1
    assert body["invoice"] is None
    assert body["document"] is None


def test_voucher_detail_is_tenant_scoped(client, voucher_seed):
    res = client.get(f"/api/v1/erp-entries/vouchers/{voucher_seed['voucher']}",
                     headers=auth("tokB"))
    assert res.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/web_api/test_voucher_detail.py -v`
Expected: FAIL with 404 on every test — the routes do not exist.

- [ ] **Step 4: Add the schema**

In `src/web_api/schemas.py`, after `VoucherGroupRead`:

```python
class DocumentRead(BaseModel):
    """The document attached to a voucher's invoice. Derived from
    `Invoice.file_id`/`File.filename` — never an independent source of truth."""

    file_id: str
    filename: str


class VoucherDetailRead(BaseModel):
    """Everything one voucher's detail panel needs, in one request.

    Exists for the cold load: `GET /erp-entries/vouchers` already embeds each
    group's entries, so a panel opened from the table has its postings already.
    A shared link arriving at an unfiltered page does not, and also needs the
    invoice, its lines, and the document descriptor.
    """

    voucher_id: str | None = None
    company_id: str
    accounting_date: date | None = None
    currency: str | None = None
    entry_count: int
    entries: list[ErpEntryRead] = []
    invoice: InvoiceDetailRead | None = None
    document: DocumentRead | None = None
```

- [ ] **Step 5: Add the routes**

In `src/web_api/routers/erp_entries.py`, **before** the `/erp-entries/{entry_id}` route (the file already documents why order matters):

```python
def _voucher_detail(session: Session, scope: TenantScope, entries: list) -> VoucherDetailRead:
    """Assemble a voucher payload from its postings.

    `_EXCLUDED_ENTRY_TYPES` deliberately does not apply: this is a lookup of a
    voucher the caller named, like `GET /erp-entries/{id}`, not a listing to
    sweep. Dropping a payment here would leave the voucher's totals unexplainable.
    """
    if not entries:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voucher not found")

    reads = [_entry_read(row) for row in entries]
    first = entries[0][0] if isinstance(entries[0], tuple) else entries[0]

    invoice_id = next((r.source_invoice_id for r in reads if r.source_invoice_id), None)
    invoice_payload = None
    document = None
    if invoice_id is not None:
        invoice = session.get(Invoice, invoice_id)
        if invoice is not None and invoice.company_id in scope.company_ids:
            lines = session.exec(
                select(InvoiceLine)
                .where(InvoiceLine.invoice_id == invoice.id)
                .order_by(InvoiceLine.id)
            ).all()
            detail = InvoiceRead.model_validate(invoice).model_dump()
            detail["lines"] = [InvoiceLineRead.model_validate(ln) for ln in lines]
            invoice_payload = InvoiceDetailRead.model_validate(detail)
            if invoice.file_id is not None:
                file_row = session.get(File, invoice.file_id)
                if file_row is not None:
                    document = DocumentRead(file_id=file_row.id, filename=file_row.filename)

    currencies = {r.currency for r in reads}
    return VoucherDetailRead(
        voucher_id=first.voucher_id,
        company_id=first.company_id,
        accounting_date=max((r.accounting_date for r in reads if r.accounting_date), default=None),
        # Claimed only when every posting agrees, matching VoucherGroupRead.
        currency=currencies.pop() if len(currencies) == 1 else None,
        entry_count=len(reads),
        entries=reads,
        invoice=invoice_payload,
        document=document,
    )


@router.get("/erp-entries/vouchers/by-entry/{entry_id}", response_model=VoucherDetailRead)
def get_voucher_by_entry(
    entry_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> VoucherDetailRead:
    """The voucher a posting belongs to, addressed by the posting.

    A group whose `voucher_id` is null is a group of one and has no shareable
    key of its own; this is how such a group is deep-linked.
    """
    rows = session.exec(
        _entry_select().where(ErpEntry.id == entry_id,
                              ErpEntry.company_id.in_(scope.company_ids))
    ).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    voucher_id = (rows[0][0] if isinstance(rows[0], tuple) else rows[0]).voucher_id
    if voucher_id is not None:
        return get_voucher_detail(voucher_id, scope, session)
    return _voucher_detail(session, scope, list(rows))


@router.get("/erp-entries/vouchers/{voucher_id}", response_model=VoucherDetailRead)
def get_voucher_detail(
    voucher_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> VoucherDetailRead:
    """One voucher's postings, its invoice with lines, and its document."""
    rows = session.exec(
        _entry_select()
        .where(ErpEntry.voucher_id == voucher_id,
               ErpEntry.company_id.in_(scope.company_ids))
        .order_by(ErpEntry.id)
    ).all()
    return _voucher_detail(session, scope, list(rows))
```

Declare `by-entry` **before** `{voucher_id}`, or the parameterized route swallows the literal segment. Add the needed imports (`File`, `Invoice`, `InvoiceLine`, `InvoiceDetailRead`, `InvoiceLineRead`, `InvoiceRead`, `DocumentRead`, `VoucherDetailRead`). Inspect what `_entry_select()` actually returns (rows vs tuples) and simplify the `isinstance` handling above to match — do not leave defensive branches for a shape you have verified.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/web_api/test_voucher_detail.py -v`
Expected: PASS.

- [ ] **Step 7: Confirm route ordering did not break the entry lookup**

Run: `uv run pytest tests/web_api/test_erp_entries.py -q`
Expected: PASS — in particular any test hitting `GET /erp-entries/{id}`.

- [ ] **Step 8: Commit**

```bash
git add src/web_api/routers/erp_entries.py src/web_api/schemas.py \
        tests/web_api/test_voucher_detail.py tests/web_api/conftest.py
git commit -m "feat(web_api): one-request voucher detail for deep-linked panels"
```

---

### Task 6: Voucher-wide audit feed

**Files:**
- Modify: `src/web_api/routers/erp_entries.py`, `src/web_api/schemas.py`
- Test: `tests/web_api/test_voucher_detail.py`

**Interfaces:**
- Consumes: `AuditLog`; `get_voucher_detail` from Task 5.
- Produces: `VoucherAuditRead` (extends `AuditLogRead` with `entity_label: str`); routes `GET /api/v1/erp-entries/vouchers/{voucher_id}/audit` and `.../by-entry/{entry_id}/audit`.

- [ ] **Step 1: Write the failing test**

```python
def test_voucher_audit_merges_invoice_and_line_rows_newest_first(client, voucher_seed):
    """One chronological story for the voucher: a per-line history cannot answer
    'what happened to this voucher' without N requests."""
    client.post(f"/api/v1/invoice-lines/{voucher_seed['line_a1']}/verify",
                json={"level_2": "Technology"}, headers=auth("tokA"))
    client.post(f"/api/v1/invoice-lines/{voucher_seed['line_a2']}/verify",
                json={}, headers=auth("tokA"))

    res = client.get(f"/api/v1/erp-entries/vouchers/{voucher_seed['voucher']}/audit",
                     headers=auth("tokA"))

    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2
    assert [r["created_at"] for r in rows] == sorted(
        (r["created_at"] for r in rows), reverse=True
    )
    assert rows[0]["action"] == "verify"
    assert rows[1]["action"] == "edit"
    # Each row names what it happened to, so the feed needs no extra lookup.
    assert all(r["entity_label"] for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web_api/test_voucher_detail.py::test_voucher_audit_merges_invoice_and_line_rows_newest_first -v`
Expected: FAIL with 404.

- [ ] **Step 3: Add the schema**

```python
class VoucherAuditRead(AuditLogRead):
    """An audit row with the thing it happened to already named.

    The same reasoning as `ErpEntryRead` resolving its account and vendor: a
    feed of foreign keys would cost the client a lookup per row.
    """

    entity_label: str
```

- [ ] **Step 4: Add the routes**

```python
@router.get("/erp-entries/vouchers/by-entry/{entry_id}/audit",
            response_model=list[VoucherAuditRead])
def list_voucher_audit_by_entry(
    entry_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[VoucherAuditRead]:
    detail = get_voucher_by_entry(entry_id, scope, session)
    return _voucher_audit(session, detail)


@router.get("/erp-entries/vouchers/{voucher_id}/audit",
            response_model=list[VoucherAuditRead])
def list_voucher_audit(
    voucher_id: str,
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> list[VoucherAuditRead]:
    """Every change to this voucher's invoice and lines, newest first.

    Newest-first because this is a feed — what happened lately. The per-line
    `GET /invoice-lines/{id}/audit` stays oldest-first: a history reads forward.
    """
    detail = get_voucher_detail(voucher_id, scope, session)
    return _voucher_audit(session, detail)


def _voucher_audit(session: Session, detail: VoucherDetailRead) -> list[VoucherAuditRead]:
    if detail.invoice is None:
        return []
    labels = {detail.invoice.id: "Invoice"}
    for index, line in enumerate(detail.invoice.lines, start=1):
        labels[line.id] = line.description or f"Line {index}"

    rows = session.exec(
        select(AuditLog)
        .where(AuditLog.entity_id.in_(list(labels)))
        .where(AuditLog.entity_type.in_(["invoice", "invoice_line"]))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    ).all()
    return [
        VoucherAuditRead(
            **AuditLogRead.model_validate(row).model_dump(),
            entity_label=labels.get(row.entity_id, row.entity_type),
        )
        for row in rows
    ]
```

Tenant scope is inherited: both routes go through the Task 5 resolvers, which already 404 outside the caller's scope. Import `AuditLog` and `VoucherAuditRead`.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/web_api/test_voucher_detail.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web_api/routers/erp_entries.py src/web_api/schemas.py tests/web_api/test_voucher_detail.py
git commit -m "feat(web_api): voucher-wide audit feed"
```

---

### Task 7: `PATCH /invoices/{id}` for parsed-header corrections

**Files:**
- Modify: `src/web_api/routers/invoices.py`, `src/web_api/schemas.py`, `src/web_api/audit.py`
- Test: `tests/web_api/test_invoices.py`

**Interfaces:**
- Consumes: `Invoice.source` (Task 1); `record_audit`, `diff_changes` from `web_api.audit`.
- Produces: `InvoiceUpdate`; `INVOICE_AUDIT_FIELDS`; route `PATCH /api/v1/invoices/{invoice_id}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_patch_rejects_an_erp_sourced_invoice(client, seed):
    """The as-posted ERP columns are evidence. The rule is enforced by the API,
    not only by the UI declining to render an input."""
    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"invoice_number": "TAMPERED"}, headers=auth("tokA"))

    assert res.status_code == 409
    assert "erp" in res.json()["detail"].lower()


def test_patch_corrects_a_parsed_invoice_and_audits_it(client, seed, engine):
    from web_api.db.models import Invoice
    with Session(engine) as s:
        inv = s.get(Invoice, seed["inv_a"])
        inv.source = "pdf_extraction"
        s.add(inv)
        s.commit()

    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"invoice_number": "INV-9"}, headers=auth("tokA"))

    assert res.status_code == 200
    assert res.json()["invoice_number"] == "INV-9"

    with Session(engine) as s:
        from web_api.db.models import AuditLog
        rows = s.exec(select(AuditLog).where(AuditLog.entity_type == "invoice")).all()
    assert len(rows) == 1
    assert rows[0].action == "edit"


def test_patch_requires_management(client, seed):
    res = client.patch(f"/api/v1/invoices/{seed['inv_a']}",
                       json={"invoice_number": "X"}, headers=auth("tok_viewerA"))
    assert res.status_code == 403
```

Remove the stray audit round-trip in the middle test before committing — it is there to show the audit row is checked in the DB, not over HTTP.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/web_api/test_invoices.py -k patch -v`
Expected: FAIL — 405 Method Not Allowed.

- [ ] **Step 3: Add the schema and audit fields**

In `schemas.py`:

```python
class InvoiceUpdate(BaseModel):
    """Corrections to an AI-parsed invoice header. Only fields the extraction
    produced — never a field the ERP posted."""

    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    total: Decimal | None = None
    tax: Decimal | None = None
    vendor_id: str | None = None
```

In `audit.py`, beside `LINE_AUDIT_FIELDS`:

```python
INVOICE_AUDIT_FIELDS = (
    "invoice_number", "invoice_date", "currency", "total", "tax", "vendor_id",
)
```

- [ ] **Step 4: Add the route**

```python
@router.patch("/invoices/{invoice_id}", response_model=InvoiceRead)
def update_invoice(
    invoice_id: str,
    body: InvoiceUpdate,
    scope: TenantScope = Depends(require_management),
    session: Session = Depends(get_session),
) -> Invoice:
    """Correct an AI-parsed invoice header (management only).

    409 for an ERP-sourced invoice: those values are evidence, and the only
    honest answer to a request to rewrite them is that they are not ours to
    rewrite.
    """
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.company_id not in scope.company_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if invoice.source != "pdf_extraction":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invoice came from the ERP; its posted values are evidence "
                   "and cannot be edited. Only AI-parsed invoices are correctable.",
        )

    before = {f: getattr(invoice, f) for f in INVOICE_AUDIT_FIELDS}
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(invoice, field, value)
    session.add(invoice)
    after = {f: getattr(invoice, f) for f in INVOICE_AUDIT_FIELDS}

    record_audit(
        session, entity_type="invoice", entity_id=invoice.id, action="edit",
        actor=scope.user_id, changes=diff_changes(before, after, INVOICE_AUDIT_FIELDS),
    )
    session.commit()
    session.refresh(invoice)
    return invoice
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/web_api/test_invoices.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/web_api/routers/invoices.py src/web_api/schemas.py src/web_api/audit.py tests/web_api/test_invoices.py
git commit -m "feat(web_api): correct AI-parsed invoice headers, refusing ERP-sourced rows"
```

---

### Task 8: Frontend plumbing — wide drawer + blob fetch + types

**Files:**
- Modify: `frontend/src/components/ui/drawer.tsx:29-40`, `frontend/src/lib/api-client.ts:107-112`, `frontend/src/lib/types.ts`
- Test: `frontend/src/components/ui/ui.test.tsx`

**Interfaces:**
- Consumes: backend schemas from Tasks 4–6.
- Produces: `DrawerContentProps.size?: 'default' | 'wide'`; `ApiClient.getBlob(path, params?) => Promise<Blob>`; TS types `VoucherDetailRead`, `VoucherAuditRead`, `DocumentRead`, `InvoiceDetailRead`, and `InvoiceRead` gaining `source`/`file_id`/`file_name`/`has_document`.

- [ ] **Step 1: Write the failing test**

In `frontend/src/components/ui/ui.test.tsx`:

```tsx
it('renders a wide drawer when asked for one', () => {
  render(
    <Drawer open>
      <DrawerContent size="wide" aria-label="Wide panel">
        <p>content</p>
      </DrawerContent>
    </Drawer>,
  )
  const panel = screen.getByLabelText('Wide panel')
  // The default drawer is max-w-md; the split layout needs room for a PDF
  // beside a field list.
  expect(panel.className).toContain('max-w-[1100px]')
  expect(panel.className).not.toContain('max-w-md')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/ui/ui.test.tsx -t "wide drawer"`
Expected: FAIL — the class is `max-w-md`.

- [ ] **Step 3: Add the size variant**

In `drawer.tsx`, add beside `sideClass`:

```tsx
const sizeClass = {
  default: 'max-w-md',
  // Wide enough for the PDF and the field list to sit side by side; capped so
  // it stays a panel over the table rather than becoming a page.
  wide: 'max-w-[1100px] w-[92vw]',
} as const
```

Add `size?: keyof typeof sizeClass` to `DrawerContentProps`, default it to `'default'` in the destructure, remove `max-w-md` from the base `cn(...)` string, and insert `sizeClass[size]` after `sideClass[side]`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/ui/ui.test.tsx`
Expected: PASS, including the existing drawer tests — the default must still be `max-w-md`.

- [ ] **Step 5: Add `getBlob` to the API client**

In `api-client.ts`, add to the `ApiClient` interface:

```ts
  /** Fetch a binary response (a PDF). `get` would try to parse it as JSON. */
  getBlob: (path: string, params?: QueryParams) => Promise<Blob>
```

And in `createApiClient`'s returned object:

```ts
    getBlob: async (path, params) => {
      const token = await getToken()
      const res = await fetch(`${API_BASE_URL}${withQuery(path, params)}`, {
        headers: {
          Accept: 'application/pdf',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })
      if (!res.ok) {
        let body: unknown
        try {
          body = await res.json()
        } catch {
          // non-JSON error body; leave undefined
        }
        throw new ApiError(res.status, `Request to ${path} failed with ${res.status}`, body)
      }
      return res.blob()
    },
```

- [ ] **Step 6: Add the TypeScript types**

In `frontend/src/lib/types.ts`, mirroring the Python schemas exactly:

```ts
export interface DocumentRead {
  file_id: string
  filename: string
}

export interface VoucherDetailRead {
  voucher_id: string | null
  company_id: string
  accounting_date: string | null
  currency: string | null
  entry_count: number
  entries: Array<ErpEntryRead>
  invoice: InvoiceDetailRead | null
  document: DocumentRead | null
}

export interface VoucherAuditRead {
  id: string
  entity_type: string
  entity_id: string
  action: string
  actor: string
  changes: Array<{ field: string; before: unknown; after: unknown }> | null
  created_at: string
  entity_label: string
}
```

Add `source: string`, `file_id: string | null`, `file_name: string | null`, `has_document: boolean` to the existing `InvoiceRead`, and add `InvoiceDetailRead extends InvoiceRead { lines: Array<InvoiceLineRead> }` if it is not already declared. Verify `changes`' real shape against `diff_changes` in `web_api/audit.py` and match it rather than assuming.

- [ ] **Step 7: Typecheck and commit**

Run: `cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/vitest run`
Expected: no type errors, all tests PASS.

```bash
git add frontend/src/components/ui/drawer.tsx frontend/src/lib/api-client.ts \
        frontend/src/lib/types.ts frontend/src/components/ui/ui.test.tsx
git commit -m "feat(frontend): wide drawer variant, blob fetch, voucher types"
```

---

### Task 9: URL-addressable panel state

**Files:**
- Modify: `frontend/src/lib/entry-search.ts`, `frontend/src/lib/types.ts` (`EntryFilters`)
- Test: `frontend/src/lib/entry-search.test.ts` (create if absent)

**Interfaces:**
- Consumes: `validateEntrySearch`, `applyFilterChange`.
- Produces: `EntryFilters` gaining `voucher?: string`, `entry?: string`, `tab?: VoucherTab`; `export type VoucherTab = 'details' | 'postings' | 'activity'`.

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, expect, it } from 'vitest'
import { applyFilterChange, validateEntrySearch } from './entry-search'

describe('validateEntrySearch', () => {
  it('carries the open voucher and tab', () => {
    expect(validateEntrySearch({ voucher: '4821', tab: 'activity' })).toMatchObject({
      voucher: '4821',
      tab: 'activity',
    })
  })

  it('drops an unknown tab rather than trusting the URL', () => {
    expect(validateEntrySearch({ voucher: '4821', tab: 'evil' }).tab).toBeUndefined()
  })
})

describe('applyFilterChange', () => {
  it('closes the panel when a filter changes', () => {
    // The open voucher may not survive the new filter; leaving it open would
    // show a panel for a row that is no longer in the list.
    const next = applyFilterChange(
      { voucher: '4821', entry: 'e1', tab: 'details' },
      { company_id: 'c2' },
    )
    expect(next.voucher).toBeUndefined()
    expect(next.entry).toBeUndefined()
    expect(next.tab).toBeUndefined()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && ./node_modules/.bin/vitest run src/lib/entry-search.test.ts`
Expected: FAIL — `voucher` is undefined.

- [ ] **Step 3: Extend the types**

In `types.ts`:

```ts
/** Which face of the voucher panel is showing. */
export type VoucherTab = 'details' | 'postings' | 'activity'
```

and add to `EntryFilters`:

```ts
  /** The open voucher, or the lone posting when it has no voucher id. */
  voucher?: string
  entry?: string
  tab?: VoucherTab
```

- [ ] **Step 4: Extend the validator**

In `entry-search.ts`:

```ts
const VOUCHER_TABS: ReadonlyArray<VoucherTab> = ['details', 'postings', 'activity']

/** Read the tab, ignoring anything not a known tab — search params are user input. */
function tab(value: unknown): VoucherTab | undefined {
  return typeof value === 'string' && (VOUCHER_TABS as ReadonlyArray<string>).includes(value)
    ? (value as VoucherTab)
    : undefined
}
```

Add to the returned object in `validateEntrySearch`:

```ts
    voucher: str(search.voucher),
    entry: str(search.entry),
    tab: tab(search.tab),
```

And in `applyFilterChange`, extend the reset:

```ts
  return { ...filters, ...changes, page: undefined, voucher: undefined, entry: undefined, tab: undefined }
```

Update that function's docstring to say the open panel closes too, and why.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && ./node_modules/.bin/vitest run src/lib/entry-search.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/entry-search.ts frontend/src/lib/types.ts frontend/src/lib/entry-search.test.ts
git commit -m "feat(frontend): put the open voucher in the URL"
```

---

### Task 10: Voucher queries

**Files:**
- Modify: `frontend/src/lib/entries.ts`
- Test: `frontend/src/lib/entries.test.ts` (create if absent)

**Interfaces:**
- Consumes: `ApiClient.get`/`getBlob` (Task 8); routes from Tasks 4–6.
- Produces: `voucherDetailQueryOptions(api, key)`, `voucherAuditQueryOptions(api, key)`, `invoiceDocumentQueryOptions(api, invoiceId)`, and `type VoucherKey = { voucher?: string; entry?: string }`.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'vitest'
import { voucherDetailQueryOptions } from './entries'

const api = { get: async () => ({}) } as never

describe('voucherDetailQueryOptions', () => {
  it('addresses a real voucher by id', () => {
    expect(voucherDetailQueryOptions(api, { voucher: '4821' }).queryKey).toContain('4821')
  })

  it('is disabled when nothing is selected', () => {
    expect(voucherDetailQueryOptions(api, {}).enabled).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && ./node_modules/.bin/vitest run src/lib/entries.test.ts`
Expected: FAIL — no such export.

- [ ] **Step 3: Implement the query options**

Append to `frontend/src/lib/entries.ts`:

```ts
/** How a voucher is addressed: by its id, or by a posting when it has none. */
export type VoucherKey = { voucher?: string; entry?: string }

/** The path segment for a key, or null when nothing is selected. */
function voucherPath(key: VoucherKey): string | null {
  if (key.voucher) return `/api/v1/erp-entries/vouchers/${encodeURIComponent(key.voucher)}`
  if (key.entry) return `/api/v1/erp-entries/vouchers/by-entry/${encodeURIComponent(key.entry)}`
  return null
}

/** One voucher's postings, invoice and document (`GET /erp-entries/vouchers/…`). */
export function voucherDetailQueryOptions(api: ApiClient, key: VoucherKey) {
  const path = voucherPath(key)
  return queryOptions({
    queryKey: [...entriesKey, 'voucher', key.voucher ?? null, key.entry ?? null],
    queryFn: () => api.get<VoucherDetailRead>(path!),
    enabled: path !== null,
  })
}

/** The voucher's change history, newest first. */
export function voucherAuditQueryOptions(api: ApiClient, key: VoucherKey) {
  const path = voucherPath(key)
  return queryOptions({
    queryKey: [...entriesKey, 'voucher-audit', key.voucher ?? null, key.entry ?? null],
    queryFn: () => api.get<Array<VoucherAuditRead>>(`${path}/audit`),
    enabled: path !== null,
  })
}

/**
 * The invoice's PDF as a Blob. Fetched through the API client rather than given
 * to an <iframe src>, because the route needs the Clerk bearer token.
 *
 * `staleTime: Infinity` because the document is immutable: refetching it would
 * re-hit the ERP for bytes that cannot have changed.
 */
export function invoiceDocumentQueryOptions(api: ApiClient, invoiceId: string | null) {
  return queryOptions({
    queryKey: [...entriesKey, 'document', invoiceId],
    queryFn: () => api.getBlob(`/api/v1/invoices/${invoiceId}/document`),
    enabled: invoiceId !== null,
    staleTime: Infinity,
    retry: false,
  })
}
```

Add the imports for `VoucherDetailRead` and `VoucherAuditRead`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && ./node_modules/.bin/vitest run src/lib/entries.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/entries.ts frontend/src/lib/entries.test.ts
git commit -m "feat(frontend): voucher detail, audit and document queries"
```

---

### Task 11: The PDF pane

**Files:**
- Create: `frontend/src/components/entries/invoice-document.tsx`
- Modify: `frontend/package.json` (via the user running `bun add`)
- Test: `frontend/src/components/entries/voucher-drawer.test.tsx`

**Interfaces:**
- Consumes: `invoiceDocumentQueryOptions` (Task 10).
- Produces: `<InvoiceDocument invoiceId={string} filename={string} />`.

- [ ] **Step 1: Ask the user to install the dependency — do not run it yourself**

Tell the user to run:

```bash
cd frontend && bun add react-pdf
```

Wait for confirmation. Never run `bun add`, `pnpm`, or `npm` — an install here can destroy `bun.lock` and break SSR.

- [ ] **Step 2: Write the failing test**

```tsx
it('tells the user when nothing is attached, without an empty viewer frame', () => {
  render(<InvoiceDocument invoiceId={null} filename={null} />)
  expect(screen.getByText(/no document/i)).toBeTruthy()
  expect(screen.queryByRole('button', { name: /download/i })).toBeNull()
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/entries/voucher-drawer.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement the pane**

Create `frontend/src/components/entries/invoice-document.tsx`. Requirements the implementation must satisfy — the spec's motion and performance section is binding here:

- `react-pdf`'s `Document`/`Page` are imported through `React.lazy` + `Suspense` so the pdf.js worker stays out of the main bundle.
- The blob from `invoiceDocumentQueryOptions` is converted to an object URL with `URL.createObjectURL`, and **revoked in the effect's cleanup** — a leaked blob URL pins the whole PDF in memory for the session.
- Pages mount through an `IntersectionObserver` (or `content-visibility: auto`) so only visible pages rasterize. `react-pdf` will otherwise render every page at once and stall the main thread on a long invoice.
- Four distinct states, none of which is a blank frame: loading (`Skeleton`), error (message from `ApiError.detail` plus a retry button that calls `refetch`), no-document, and rendered.
- Controls: previous/next page with the current page and total, zoom out/in, and download. Every icon-only control gets an `aria-label`; all are ≥44×44px hit area.
- The page sits on a neutral surround (`bg-muted`) with the page itself elevated — never a white sheet flush against a dark theme.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/entries/voucher-drawer.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/entries/invoice-document.tsx frontend/package.json frontend/bun.lock \
        frontend/src/components/entries/voucher-drawer.test.tsx
git commit -m "feat(frontend): PDF pane with lazy pdf.js and visible-page rendering"
```

---

### Task 12: Panel shell, postings tab, activity tab

**Files:**
- Create: `voucher-drawer.tsx`, `voucher-postings-tab.tsx`, `voucher-activity-tab.tsx` in `frontend/src/components/entries/`
- Delete: `frontend/src/components/entries/entry-drawer.tsx`
- Test: `frontend/src/components/entries/voucher-drawer.test.tsx`

**Interfaces:**
- Consumes: `DrawerContent size="wide"` (Task 8), `VoucherTab` (Task 9), `InvoiceDocument` (Task 11), `VoucherDetailRead`/`VoucherAuditRead`.
- Produces: `<VoucherDrawer detail loading auditRows auditLoading tab open onTabChange onOpenChange />` — presentational, no queries, so tests render it directly like `EntriesPanel`.

- [ ] **Step 1: Write the failing tests**

```tsx
it('shows the document beside the detail when an invoice is attached', () => {
  render(<VoucherDrawer {...props({ detail: withInvoice })} />)
  expect(screen.getByLabelText('Voucher detail').className).toContain('max-w-[1100px]')
  expect(screen.getByRole('tab', { name: /details/i })).toBeTruthy()
})

it('collapses to postings when the voucher has no invoice', () => {
  // Most vouchers are journal entries with nothing to review. A wide panel of
  // empty frames would be worse than a small honest one.
  render(<VoucherDrawer {...props({ detail: journalOnly })} />)
  expect(screen.getByLabelText('Voucher detail').className).not.toContain('max-w-[1100px]')
  expect(screen.queryByRole('tab', { name: /details/i })).toBeNull()
  expect(screen.queryByRole('tab', { name: /postings/i })).toBeTruthy()
})

it('renders the audit feed newest first with what changed', () => {
  render(<VoucherDrawer {...props({ detail: withInvoice, tab: 'activity', auditRows: AUDIT })} />)
  const items = screen.getAllByRole('listitem')
  expect(within(items[0]).getByText(/corrected/i)).toBeTruthy()
})
```

Build `props()` as a helper returning a complete `VoucherDrawerProps` with overrides, following the `entry()` fixture-builder pattern already in `entries-panel.test.tsx`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/entries/voucher-drawer.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Build the postings tab**

Create `voucher-postings-tab.tsx`. Move `Row`, `Value` and `ConversionRows` from `entry-drawer.tsx` **unchanged** — they already explain a converted figure well, and rewriting them would risk the FX presentation rules for no gain. Render one collapsible block per posting: account code + name in the header with the signed amount, and the full field list inside. ERP values use the read-only treatment (muted surface, no input affordance).

- [ ] **Step 4: Build the activity tab**

Create `voucher-activity-tab.tsx`. A `<ul>` of audit rows, newest first as the API returns them. Each row: actor (or "system"), the action verb, the `entity_label`, the field-level before → after from `changes`, and a relative timestamp with the absolute one in a `title`. Empty state: "No changes recorded for this voucher yet." Stagger the entrance by ~40ms per row on first paint only, inside a `prefers-reduced-motion` guard.

- [ ] **Step 5: Build the shell**

Create `voucher-drawer.tsx`. It decides the layout from the data: `detail.invoice !== null` gives `size="wide"` with the PDF column and all three tabs; otherwise `size="default"` with Postings and Activity only. Below 1024px the split stacks and the PDF becomes its own tab (Tailwind `lg:` breakpoint). Header shows voucher id, supplier, date, posting count and total. The tab is controlled from props so it stays in the URL.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/entries/`
Expected: PASS.

- [ ] **Step 7: Delete the old drawer**

Delete `frontend/src/components/entries/entry-drawer.tsx` and remove its import from `entries-panel.tsx`. Confirm nothing else references it: `grep -rn "entry-drawer\|EntryDrawer" frontend/src`.

- [ ] **Step 8: Commit**

```bash
git add -A frontend/src/components/entries/
git commit -m "feat(frontend): voucher panel shell with postings and activity"
```

---

### Task 13: Details tab and line correction

**Files:**
- Create: `voucher-details-tab.tsx`, `line-category-editor.tsx`
- Test: `frontend/src/components/entries/voucher-drawer.test.tsx`

**Interfaces:**
- Consumes: `VoucherDetailRead.invoice.lines`; `POST /invoice-lines/{id}/verify`.
- Produces: `<VoucherDetailsTab invoice onVerifyLine />`, where `onVerifyLine(lineId, corrections) => Promise<void>`.

- [ ] **Step 1: Write the failing tests**

```tsx
it('renders ERP header values as evidence, not as inputs', () => {
  // Provenance decides affordance. A disabled input still reads as tappable.
  render(<VoucherDetailsTab invoice={erpInvoice} onVerifyLine={vi.fn()} />)
  expect(screen.getByText('INV-2026-0412')).toBeTruthy()
  expect(screen.queryByLabelText(/invoice number/i)).toBeNull()
})

it('lets a parsed header be corrected', () => {
  render(<VoucherDetailsTab invoice={{ ...erpInvoice, source: 'pdf_extraction' }} onVerifyLine={vi.fn()} />)
  expect(screen.getByLabelText(/invoice number/i)).toBeTruthy()
})

it('submits a corrected category and shows the confidence being judged', async () => {
  const onVerifyLine = vi.fn().mockResolvedValue(undefined)
  render(<VoucherDetailsTab invoice={erpInvoice} onVerifyLine={onVerifyLine} />)

  fireEvent.change(screen.getByLabelText(/level 2/i), { target: { value: 'Office supplies' } })
  fireEvent.click(screen.getByRole('button', { name: /accept/i }))

  await waitFor(() =>
    expect(onVerifyLine).toHaveBeenCalledWith('l2', { level_2: 'Office supplies' }),
  )
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/entries/voucher-drawer.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Build the line editor**

Create `line-category-editor.tsx`. One line: description and amount, the three category levels as inputs, the confidence rendered as a labelled bar (with the numeric value in text — never colour alone), the rationale in a de-emphasised block, and Accept / Cancel. Only dirty fields go into the corrections object, so a plain accept records `verify` rather than `edit` — the backend distinguishes them on exactly that. Disable the submit while in flight and show the pending state on the button.

- [ ] **Step 4: Build the details tab**

Create `voucher-details-tab.tsx`. Two groups: the invoice header (read-only text for `source === 'erp'`, labelled inputs for `pdf_extraction`, with a provenance badge either way) and the line list, each line an editor. Provenance badges must be text + icon, never a colour swatch alone.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/entries/`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/entries/
git commit -m "feat(frontend): correct AI categorization from the voucher panel"
```

---

### Task 14: Wire the panel into the route

**Files:**
- Modify: `frontend/src/routes/_authed/entries.tsx`, `frontend/src/components/entries/entries-panel.tsx`
- Test: `frontend/src/components/entries/entries-panel.test.tsx`

**Interfaces:**
- Consumes: everything above.
- Produces: `EntriesPanelProps` losing `selectedEntry`/`selectedEntryLoading`/`selectedEntryId`, gaining `voucherDetail`, `voucherLoading`, `auditRows`, `auditLoading`, `tab`, `onTabChange`; `onSelectEntry` keeps its name and now navigates.

- [ ] **Step 1: Write the failing test**

```tsx
it('opens the panel for the voucher named in the URL', () => {
  render(<EntriesPanel {...props({ filters: { voucher: '4821' }, voucherDetail: DETAIL })} />)
  expect(screen.getByLabelText('Voucher detail')).toBeTruthy()
})

it('asks to open a voucher by its id, and by entry id when it has none', () => {
  const onSelectEntry = vi.fn()
  render(<EntriesPanel {...props({ onSelectEntry })} />)
  fireEvent.click(screen.getAllByRole('button', { name: /view voucher/i })[0])
  expect(onSelectEntry).toHaveBeenCalledWith({ voucher: 'V-1042', entry: 'e1' })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && ./node_modules/.bin/vitest run src/components/entries/entries-panel.test.tsx`
Expected: FAIL — the panel still renders the deleted `EntryDrawer` contract.

- [ ] **Step 3: Rewire the panel**

In `entries-panel.tsx`, replace the `EntryDrawer` block with `VoucherDrawer`, driven by `filters.voucher`/`filters.entry` rather than a separate `selectedEntryId`. Open state is `filters.voucher !== undefined || filters.entry !== undefined`.

- [ ] **Step 4: Rewire the route**

In `routes/_authed/entries.tsx`: delete the `selectedEntryId` `useState` and the `entryQueryOptions` call; add `useQuery(voucherDetailQueryOptions(api, {voucher: filters.voucher, entry: filters.entry}))` and the audit query; make `onSelectEntry` navigate (`navigate({ search: { ...filters, voucher, entry } })`) and `onTabChange` set `tab`. Add a `useMutation` for verify that invalidates `entriesKey` on success, so the voucher detail, the audit feed and the groups list all refresh — verifying a line changes the invoice rollup the table shows.

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/vitest run`
Expected: no type errors, all PASS.

- [ ] **Step 6: Verify in the browser — hand the commands to the user**

Ask the user to run, in three terminals:

```bash
uvicorn mock_erp.main:app --reload --port 8001
uvicorn web_api.app:app --reload
cd frontend && bun run dev
```

Then ask them to confirm: opening a voucher shows the PDF; copying the URL into a new tab reopens the same panel over the same filters; correcting a line's category persists and appears in Activity; a journal-entry voucher opens the collapsed panel. Do not launch these yourself.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/_authed/entries.tsx frontend/src/components/entries/
git commit -m "feat(frontend): open the voucher panel from the entries table and the URL"
```

---

### Task 15: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Document the new surface**

Add to the endpoints section: `GET /erp-entries/vouchers/{voucher_id}`, `.../by-entry/{entry_id}`, both `/audit` variants, `GET /invoices/{id}/document`, and `PATCH /invoices/{id}`. State that the voucher detail and lookup routes are **not** subject to `_EXCLUDED_ENTRY_TYPES`, and why.

Add to the categorization section: `Invoice.source` decides what may be corrected — `erp` rows are evidence, `pdf_extraction` rows are correctable — and `PATCH /invoices/{id}` returns 409 for the former.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: record the voucher detail surface and invoice provenance"
```

---

## Self-Review

**Spec coverage:** provenance rule → Tasks 1, 7, 13. PDF end-to-end → Tasks 2, 3, 4, 11. Voucher detail read → Task 5. Audit feed → Tasks 6, 12. URL addressability → Tasks 9, 14. Split/collapsed layout → Tasks 8, 12. Motion and rendering rules → Tasks 11, 12. Testing section → covered per task. No spec requirement is unassigned.

**Naming consistency checked across tasks:** `DocumentPayload` (3→4), `connector_for_integration` (4→5), `VoucherDetailRead` (5→6, 8, 10), `VoucherAuditRead` (6→8, 10), `VoucherKey` (10→14), `size="wide"` (8→12), `VoucherTab` (9→12, 14), `INVOICE_AUDIT_FIELDS` (7).

**Known rough edges the implementer must resolve rather than paper over:**

- Task 3's `mock_erp_base_url` fixture assumes `httpx`; verify the connector's real HTTP client first.
- Task 5's `_entry_select()` row shape (rows vs tuples) must be checked and the defensive `isinstance` collapsed to the real shape.
