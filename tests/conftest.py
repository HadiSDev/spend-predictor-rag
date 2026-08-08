import pytest


@pytest.fixture
def mock_erp_connector():
    """A MockErpConnector wired to the mock ERP app, in-process.

    Mirrors ``tests/test_mock_erp.py``'s ``connector_over_app`` fixture:
    ``TestClient`` is a synchronous ``httpx.Client`` bound to the ASGI app
    (entering it fires startup, i.e. the data generator). Assigning it as
    the connector's own ``_http`` — an attribute the connector already
    lazily builds itself — gives every fetch a real HTTP round-trip through
    the actual FastAPI handlers, without a live server and without touching
    any private httpx internals.
    """
    from fastapi.testclient import TestClient
    from mock_erp.main import app
    from web_api.connectors.mock import MockErpConnector

    client = TestClient(app)
    client.__enter__()
    connector = MockErpConnector({"api_key": "mock-secret"})
    connector._http = client
    yield connector
    client.__exit__(None, None, None)
