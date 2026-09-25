"""Savings recommendation engine."""


def find_consolidation_savings(tenant_id: str) -> list[dict]:
    ...


def find_alternative_savings(tenant_id: str) -> list[dict]:
    ...


def find_bulk_savings(tenant_id: str) -> list[dict]:
    ...


def all_recommendations(tenant_id: str) -> list[dict]:
    ...
