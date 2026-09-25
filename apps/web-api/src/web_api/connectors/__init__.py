"""ERP connector factory."""
from .base import (
    CredentialField,
    ErpAuthError,
    ErpConnectionError,
    ErpConnector,
    ErpDataError,
    ErpRateLimitError,
)
from .billy import BillyConnector
from .mock import MockErpConnector
from .registry import (
    available_connectors,
    connector_catalog,
    connector_class,
    get_connector,
    register_connector,
)

register_connector("mock", MockErpConnector)
register_connector("billy", BillyConnector)

__all__ = [
    "CredentialField",
    "ErpAuthError",
    "ErpConnectionError",
    "ErpConnector",
    "ErpDataError",
    "ErpRateLimitError",
    "available_connectors",
    "connector_catalog",
    "connector_class",
    "get_connector",
    "register_connector",
]
