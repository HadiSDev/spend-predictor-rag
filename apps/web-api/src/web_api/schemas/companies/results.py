"""What creating or updating a company returns."""
from __future__ import annotations

from ..companies.company import CompanyRead
from ..erp.integrations import ErpIntegrationRead


class CompanyUpdateResult(CompanyRead):
    """What `PATCH /companies` returns: the company plus what the change cost."""

    stale_lines: int = 0


class CompanyCreateResult(CompanyRead):
    """What `POST /companies` returns: the company plus the integration it got."""

    integration: ErpIntegrationRead
