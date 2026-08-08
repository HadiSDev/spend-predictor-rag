def test_fetch_invoice_document_returns_pdf_bytes(mock_erp_connector):
    invoices = mock_erp_connector.fetch_invoices()
    voucher_id = invoices[0].voucher_id

    payload = mock_erp_connector.fetch_invoice_document(voucher_id)

    assert payload is not None
    assert payload.media_type == "application/pdf"
    assert payload.content.startswith(b"%PDF-")
    assert payload.filename.endswith(".pdf")


def test_fetch_invoice_document_returns_none_for_a_voucher_with_no_scan(mock_erp_connector):
    # Distinct from a failed fetch, which raises: None means "nothing attached".
    assert mock_erp_connector.fetch_invoice_document("99999999") is None
