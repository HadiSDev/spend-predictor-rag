"""Vendor redundancy detection."""


def find_same_category_overlaps(tenant_id: str) -> list[dict]:
    ...


def find_semantic_overlaps(tenant_id: str, threshold: float = 0.7) -> list[dict]:
    ...


def benchmark(tenant_id: str) -> dict:
    ...
