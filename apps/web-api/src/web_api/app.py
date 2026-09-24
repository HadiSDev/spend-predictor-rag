"""FastAPI application factory for the Clerk-authenticated web API.

Run either way:
    uvicorn web_api.app:app --reload --reload-dir apps/web-api/src
    uv run apps/web-api/src/web_api/app.py   # launches uvicorn (dev, reloads apps/web-api/src/)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from scalar_fastapi import get_scalar_api_reference

# Absolute imports (not `from . import …`) so this module also works when run
# as a file (`python apps/web-api/src/web_api/app.py`), where it isn't part of a package.
from web_api import config
from web_api.routers import (
    companies,
    erp_entries,
    erp_integrations,
    invoice_lines,
    invoices,
    organization,
    reports,
    spend_trees,
    users,
    vendors,
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

    # Browser front-end access. Empty origins ⇒ no cross-origin access (prod is
    # explicit); read at call time so tests can configure it.
    if config.WEB_API_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.WEB_API_CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
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
    app.include_router(reports.router)
    app.include_router(spend_trees.router)
    app.include_router(users.router)
    app.include_router(vendors.router)
    app.include_router(webhooks.router)
    return app


app = create_app()


if __name__ == "__main__":
    import pathlib

    import uvicorn

    # Watch only this app's src/ so the reloader never touches data dirs like pgdata/
    # (which are owned by the Postgres container and raise permission errors).
    src_dir = str(pathlib.Path(__file__).resolve().parents[1])
    uvicorn.run(
        "web_api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[src_dir],
    )
