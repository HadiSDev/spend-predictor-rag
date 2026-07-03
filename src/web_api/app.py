"""FastAPI application factory for the Clerk-authenticated web API.

Run with:  uvicorn web_api.app:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from scalar_fastapi import get_scalar_api_reference

from .routers import (
    companies,
    erp_entries,
    erp_integrations,
    invoice_lines,
    invoices,
    organization,
    webhooks,
)


def create_app() -> FastAPI:
    # Scalar is the API reference UI, served at /scalar. Disable FastAPI's
    # built-in Swagger/ReDoc so Scalar is the single docs surface (OpenAPI JSON
    # stays at /openapi.json, which Scalar consumes).
    app = FastAPI(
        title="Spend Predictor Web API",
        version="0.1.0",
        description="Clerk-authenticated API for reviewing raw ERP spend data.",
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/api/v1/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/scalar", include_in_schema=False)
    def scalar_docs() -> HTMLResponse:
        return get_scalar_api_reference(
            openapi_url=app.openapi_url,
            title=app.title,
        )

    app.include_router(companies.router)
    app.include_router(invoices.router)
    app.include_router(invoice_lines.router)
    app.include_router(erp_entries.router)
    app.include_router(erp_integrations.router)
    app.include_router(organization.router)
    app.include_router(webhooks.router)
    return app


app = create_app()
