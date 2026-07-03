"""ERP connector factory.

Usage::

    connector = get_connector("mock", {"api_key": "mock-secret", "base_url": "http://localhost:8001"})
    connector.authorize(config)
    invoices = connector.fetch_invoices()
"""
from .base import ErpConnector, ErpAuthError, ErpConnectionError, ErpDataError, ErpRateLimitError


_CONNECTORS: dict[str, type[ErpConnector]] = {}


def register_connector(name: str, cls: type[ErpConnector]) -> None:
    _CONNECTORS[name] = cls


def get_connector(name: str, config: dict | None = None) -> ErpConnector:
    cls = _CONNECTORS.get(name)
    if cls is None:
        available = ", ".join(sorted(_CONNECTORS))
        msg = f"Unknown connector {name!r}. Available: {available}"
        raise ValueError(msg)
    return cls(config or {})


def available_connectors() -> list[str]:
    """Sorted list of registered connector (erp_type) names."""
    return sorted(_CONNECTORS)


# Import built-in connectors for their registration side effects. Kept at the
# bottom so ``register_connector`` is defined before they import it.
from . import mock as _mock  # noqa: E402,F401
