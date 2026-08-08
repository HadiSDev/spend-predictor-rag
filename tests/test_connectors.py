import pytest

from web_api.connectors.mock import MockErpConnector


@pytest.fixture
def connector(mock_erp_base_url):
    return MockErpConnector({"base_url": mock_erp_base_url})


def test_fetch_invoice_document_returns_pdf_bytes(connector):
    invoices = connector.fetch_invoices()
    voucher_id = invoices[0].voucher_id

    payload = connector.fetch_invoice_document(voucher_id)

    assert payload is not None
    assert payload.media_type == "application/pdf"
    assert payload.content.startswith(b"%PDF-")
    assert payload.filename.endswith(".pdf")


def test_fetch_invoice_document_returns_none_for_a_voucher_with_no_scan(connector):
    # Distinct from a failed fetch, which raises: None means "nothing attached".
    assert connector.fetch_invoice_document("99999999") is None
