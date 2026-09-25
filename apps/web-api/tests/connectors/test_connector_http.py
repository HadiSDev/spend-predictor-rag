"""Tests for the shared HTTP connector base and the pagination strategies."""
import httpx
import pytest

from web_api.connectors.base import (
    ErpAuthError,
    ErpConnectionError,
    ErpDataError,
    ErpRateLimitError,
)
from web_api.connectors.http import HttpErpConnector
from web_api.connectors.mock import MockErpConnector
from web_api.connectors.pagination import (
    NextLinkPaginator,
    PageNumberPaginator,
    SkipPagesPaginator,
)


class _Probe(HttpErpConnector):
    """Minimal concrete connector: only the two seams, no ERP mapping."""

    retry_backoff_seconds = 0.0

    def __init__(self, config=None, token="t0", http_client=None):
        super().__init__(config or {}, http_client)
        self.token = token
        self.auth_calls = 0

    def _auth_headers(self):
        self.auth_calls += 1
        return {"x-token": self.token}

    def authorize(self):
        return self.token

    def test_connection(self):
        return True

    def fetch_accounts(self):
        return []

    def fetch_vendors(self, since=None):
        return []

    def fetch_invoices(self, since=None):
        return []

    def fetch_entries(self, since=None, account_codes=None):
        return []

    def fetch_invoice_scan(self, voucher_id):
        return None

    def fetch_invoice_document(self, voucher_id):
        return None


def _probe(handler, **kwargs):
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://erp")
    return _Probe(http_client=client, **kwargs)


def test_auth_headers_are_re_evaluated_on_every_request():
    seen = []

    def handler(request):
        seen.append(request.headers["x-token"])
        return httpx.Response(200, json={})

    connector = _probe(handler)
    connector._get("/a")
    connector.token = "t1"
    connector._get("/b")

    assert seen == ["t0", "t1"]


def test_injected_client_is_used_and_no_socket_is_opened():
    connector = _probe(lambda request: httpx.Response(200, json={"ok": True}))
    assert connector._get("/health") == {"ok": True}


@pytest.mark.parametrize("status", [401, 403])
def test_unauthorized_raises_auth_error(status):
    connector = _probe(lambda request: httpx.Response(status, text="nope"))
    with pytest.raises(ErpAuthError):
        connector._get("/a")


def test_unexpected_status_raises_data_error():
    connector = _probe(lambda request: httpx.Response(418, text="teapot"))
    with pytest.raises(ErpDataError):
        connector._get("/a")


def test_transport_failure_raises_connection_error():
    def handler(request):
        raise httpx.ConnectError("unreachable", request=request)

    connector = _probe(handler)
    with pytest.raises(ErpConnectionError):
        connector._get("/a")


def test_malformed_json_raises_data_error():
    connector = _probe(lambda request: httpx.Response(200, text="<html>not json"))
    with pytest.raises(ErpDataError):
        connector._get("/a")


def test_persistent_rate_limit_raises_the_rate_limit_error():
    connector = _probe(
        lambda request: httpx.Response(429, text="slow down", headers={"retry-after": "0"})
    )
    with pytest.raises(ErpRateLimitError) as excinfo:
        connector._get("/a")
    assert excinfo.value.retry_after == 0


def test_rate_limit_error_carries_no_delay_when_the_erp_names_none():
    connector = _probe(lambda request: httpx.Response(429, text="slow down"))
    with pytest.raises(ErpRateLimitError) as excinfo:
        connector._get("/a")
    assert excinfo.value.retry_after is None


def test_a_transient_server_error_is_retried_and_then_succeeds():
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503, text="restarting")
        return httpx.Response(200, json={"ok": True})

    connector = _probe(handler)
    assert connector._get("/a") == {"ok": True}
    assert attempts["n"] == 2


def test_retries_are_bounded_and_the_error_escapes():
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(503, text="down")

    connector = _probe(handler)
    with pytest.raises(ErpConnectionError):
        connector._get("/a")
    assert attempts["n"] == _Probe.max_retries + 1


def test_raw_fetch_returns_none_on_404_and_reads_the_filename():
    def handler(request):
        if request.url.path == "/missing":
            return httpx.Response(404)
        return httpx.Response(
            200,
            content=b"%PDF-1.4",
            headers={"content-disposition": 'attachment; filename="v1.pdf"'},
        )

    connector = _probe(handler)
    assert connector._request_raw("/missing") is None
    assert connector._request_raw("/there") == (b"%PDF-1.4", "v1.pdf")


def test_raw_fetch_can_omit_the_credential():
    seen = []

    def handler(request):
        seen.append("x-token" in request.headers)
        return httpx.Response(200, content=b"x")

    connector = _probe(handler)
    connector._request_raw("/doc", authenticated=True)
    connector._request_raw("/doc", authenticated=False)

    assert seen == [True, False]


def test_page_number_paging_accumulates_every_page():
    def handler(request):
        page = int(request.url.params["page"])
        items = [{"id": f"{page}-{i}"} for i in range(2)]
        return httpx.Response(200, json={"collection": items, "pagination": {"total": 6}})

    connector = _probe(handler)
    connector.paginator = PageNumberPaginator(page_size=2)
    items = connector._paginate("/things")

    assert [i["id"] for i in items] == ["1-0", "1-1", "2-0", "2-1", "3-0", "3-1"]


def test_page_number_paging_stops_on_an_empty_page_despite_the_total():
    def handler(request):
        page = int(request.url.params["page"])
        items = [{"id": page}] if page == 1 else []
        return httpx.Response(200, json={"collection": items, "pagination": {"total": 99}})

    connector = _probe(handler)
    connector.paginator = PageNumberPaginator(page_size=1)
    assert len(connector._paginate("/things")) == 1


def test_skip_pages_paging_follows_the_next_page_indicator():
    def handler(request):
        skipped = int(request.url.params["skippages"])
        has_next = skipped < 2
        return httpx.Response(
            200,
            json={
                "collection": [{"id": skipped}],
                "pagination": {"nextPage": "/things?skippages=1" if has_next else None},
            },
        )

    connector = _probe(handler)
    connector.paginator = SkipPagesPaginator(page_size=1)
    assert [i["id"] for i in connector._paginate("/things")] == [0, 1, 2]


def test_cursor_paging_stops_when_the_next_link_is_absent():
    def handler(request):
        if "page" not in request.url.params:
            return httpx.Response(
                200,
                json={"value": [{"id": 1}], "@odata.nextLink": "http://erp/things?page=2"},
            )
        return httpx.Response(200, json={"value": [{"id": 2}]})

    connector = _probe(handler)
    connector.paginator = NextLinkPaginator()
    assert [i["id"] for i in connector._paginate("/things")] == [1, 2]


def test_mock_connector_now_raises_the_rate_limit_error_on_429():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(429, text="slow")),
        base_url="http://erp",
    )
    connector = MockErpConnector({}, http_client=client)
    connector.retry_backoff_seconds = 0.0

    with pytest.raises(ErpRateLimitError):
        connector.fetch_accounts()
