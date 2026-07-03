"""Savings recommendation engine.

Three recommendation types, in priority order:
  1. Consolidation — redundant vendors in same category.
  2. Alternative search — web-researched cheaper alternatives.
  3. Bulk negotiation signal — spend tier suggests discount opportunity.
"""


def find_consolidation_savings(tenant_id: str) -> list[dict]:
    ...


def find_alternative_savings(tenant_id: str) -> list[dict]:
    ...


def find_bulk_savings(tenant_id: str) -> list[dict]:
    ...


def all_recommendations(tenant_id: str) -> list[dict]:
    ...
