import pytest


@pytest.fixture
def mock_erp_base_url(monkeypatch):
    """Serve the mock ERP in-process and route connector HTTP calls to it.

    ``httpx.ASGITransport`` in the installed httpx version (0.28) only
    implements the *async* transport interface (``handle_async_request``),
    but the connector's ``httpx.Client`` is synchronous — driving it with a
    bare ``ASGITransport`` raises ``AttributeError: 'ASGITransport' object
    has no attribute 'handle_request'``. Starlette's ``TestClient`` builds a
    transport that bridges an ASGI app to sync calls via a blocking portal;
    reuse that transport instead of trying to drive ASGITransport
    synchronously.
    """
    from mock_erp.main import app, regenerate_data
    from starlette.testclient import TestClient
    import httpx

    regenerate_data()
    transport = TestClient(app)._transport
    real_client = httpx.Client

    def _client(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _client)
    return "http://mock-erp"
