"""The registry of ERP connector types, keyed by ``erp_type``."""
from .base import ErpConnector

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


def connector_catalog() -> list[tuple[str, type[ErpConnector]]]:
    """``(erp_type, class)`` for every registered connector, sorted by name."""
    return [(name, _CONNECTORS[name]) for name in sorted(_CONNECTORS)]


def connector_class(name: str) -> type[ErpConnector] | None:
    """The registered class for ``name``, or ``None`` if unknown."""
    return _CONNECTORS.get(name)
