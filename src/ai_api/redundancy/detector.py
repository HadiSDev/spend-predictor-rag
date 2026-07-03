"""Vendor redundancy detection.

Detects multiple vendors supplying the same or similar products/categories.
Two strategies:
  A. Jaccard overlap of line-item descriptions within the same L2 category.
  B. Semantic similarity of vendor + product description vectors via Qdrant.

All scoped by tenant_id. Benchmarked against synthetic ground truth.
"""


def find_same_category_overlaps(tenant_id: str) -> list[dict]:
    ...


def find_semantic_overlaps(tenant_id: str, threshold: float = 0.7) -> list[dict]:
    ...


def benchmark(tenant_id: str) -> dict:
    ...
