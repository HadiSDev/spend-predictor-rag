"""SQL-based spend aggregation and rollups.

Provides time-series spend by category/vendor for the dashboard and
procurement agent inputs. All queries are scoped by tenant_id.
"""


def spend_by_category(tenant_id: str, period: str = "month") -> list[dict]:
    ...


def spend_by_vendor(tenant_id: str, period: str = "month") -> list[dict]:
    ...


def top_vendors(tenant_id: str, limit: int = 20) -> list[dict]:
    ...


def spend_trend(tenant_id: str, category_level_2: str | None = None) -> list[dict]:
    ...


def total_spend(tenant_id: str, since: str | None = None) -> float:
    ...
