"""Mock ERP API server — FastAPI app.

Provides endpoints matching the e-conomic REST API shape so the
MockErpConnector can exercise the full sync pipeline.
"""

from __future__ import annotations

import hashlib
import os
from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from .auth import verify_auth
from .data.accounts import ACCOUNTS
from .data.entries import generate as generate_entries
from .data.invoices import generate as generate_invoices
from .data.vendors import build_vendors, get_cheaper_alternatives

_GENERATION_SEED = int(os.getenv("MOCK_ERP_SEED", "42"))
_N_MONTHS = int(os.getenv("MOCK_ERP_MONTHS", "12"))
_AVG_INVOICES_PER_MONTH = int(os.getenv("MOCK_ERP_AVG_INVOICES", "15"))
_START_DATE = date.fromisoformat(os.getenv("MOCK_ERP_START_DATE", "2025-07-01"))

app = FastAPI(
    title="Mock ERP API",
    version="0.1.0",
    description="Simulates an e-conomic-style REST API for development and testing.",
)

_ACCOUNTS: list[dict] = []
_VENDORS: list[dict] = []
_INVOICES: list[dict] = []
_ENTRIES: list[dict] = []
_GENERATED_AT: str | None = None
_CHEAPER_ALTERNATIVES: dict[int, int] = {}


def regenerate_data() -> None:
    global _ACCOUNTS, _VENDORS, _INVOICES, _ENTRIES, _GENERATED_AT, _CHEAPER_ALTERNATIVES
    _ACCOUNTS = [{
        "accountNumber": a["accountNumber"],
        "name": a["name"],
        "accountType": a["accountType"],
        "parentAccountNumber": a["parentAccountNumber"],
        "withVat": a.get("withVat", False),
        "balance": round(a["accountNumber"] * 1000.0, 2),  # fake balance
    } for a in ACCOUNTS]
    _VENDORS = build_vendors()
    _INVOICES = generate_invoices(
        seed=_GENERATION_SEED,
        n_months=_N_MONTHS,
        avg_invoices_per_month=_AVG_INVOICES_PER_MONTH,
        start_date=_START_DATE,
    )
    _ENTRIES = generate_entries(_INVOICES, seed=_GENERATION_SEED)
    _CHEAPER_ALTERNATIVES = get_cheaper_alternatives()
    _GENERATED_AT = datetime.utcnow().isoformat()


@app.on_event("startup")
async def on_startup() -> None:
    regenerate_data()


def _paginate(
    collection: list[dict],
    page: int,
    page_size: int,
) -> dict:
    total = len(collection)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "collection": collection[start:end],
        "pagination": {
            "maxPageSize": page_size,
            "page": page,
            "results": min(total - start, page_size),
            "total": total,
        },
    }


# ── Health ──────────────────────────────────────────────────────────────────


@app.get("/api/v1/health")
async def health() -> dict:
    return {
        "status": "ok",
        "mode": "mock",
        "dataGenerated": _GENERATED_AT or "",
        "stats": {
            "accounts": len(_ACCOUNTS),
            "vendors": len(_VENDORS),
            "invoices": len(_INVOICES),
            "lines": sum(len(inv.get("lines", [])) for inv in _INVOICES),
            "entries": len(_ENTRIES),
        },
    }


@app.post("/api/v1/data/regenerate")
async def regenerate(_=None) -> dict:
    regenerate_data()
    return {"status": "ok", "generatedAt": _GENERATED_AT}


@app.get("/api/v1/cheaper-alternatives")
async def cheaper_alternatives(_=None) -> dict:
    """Return {expensive_vendor_number: cheap_vendor_number} pairs."""
    return _CHEAPER_ALTERNATIVES


# ── Accounts ────────────────────────────────────────────────────────────────


@app.get("/api/v1/accounts")
async def list_accounts(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
) -> dict:
    return _paginate(_ACCOUNTS, page, pageSize)


@app.get("/api/v1/accounts/{account_number}")
async def get_account(account_number: int) -> dict:
    for a in _ACCOUNTS:
        if a["accountNumber"] == account_number:
            return a
    raise HTTPException(status_code=404, detail="Account not found")


# ── Vendors ─────────────────────────────────────────────────────────────────


@app.get("/api/v1/vendors")
async def list_vendors(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
) -> dict:
    return _paginate(_VENDORS, page, pageSize)


@app.get("/api/v1/vendors/{vendor_number}")
async def get_vendor(vendor_number: int) -> dict:
    for v in _VENDORS:
        if v["vendorNumber"] == vendor_number:
            return v
    raise HTTPException(status_code=404, detail="Vendor not found")


# ── Purchase invoices ───────────────────────────────────────────────────────


@app.get("/api/v1/purchase-invoices")
async def list_invoices(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
) -> dict:
    return _paginate(_INVOICES, page, pageSize)


@app.get("/api/v1/purchase-invoices/{invoice_number}")
async def get_invoice(invoice_number: int) -> dict:
    for inv in _INVOICES:
        if inv["purchaseInvoiceNumber"] == invoice_number:
            return inv
    raise HTTPException(status_code=404, detail="Invoice not found")


# ── Entries (GL postings) ────────────────────────────────────────────────────


@app.get("/api/v1/entries")
async def list_entries(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    since: str | None = Query(None, description="ISO date; return entries on/after this date"),
    accounts: str | None = Query(None, description="Comma-separated account codes to filter by"),
) -> dict:
    collection = _ENTRIES
    if since:
        collection = [e for e in collection if e.get("date", "") >= since]
    if accounts is not None:
        wanted = {a.strip() for a in accounts.split(",") if a.strip()}
        collection = [
            e for e in collection
            if str(e.get("account", {}).get("accountNumber", "")) in wanted
        ]
    return _paginate(collection, page, pageSize)


# ── Auth wrapper (optional — /api/v1/* routes behind verify_auth) ──────────


@app.middleware("http")
async def auth_middleware(request, call_next):
    if request.url.path.startswith("/api/v1/") and request.url.path not in (
        "/api/v1/health",
        "/docs",
        "/openapi.json",
    ):
        token = request.headers.get("x-app-secret-token")
        if token != "mock-secret":
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})
    return await call_next(request)
