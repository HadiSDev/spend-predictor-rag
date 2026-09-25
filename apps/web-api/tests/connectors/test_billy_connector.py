"""Billy connector tests, served from scrubbed captures of a real organization."""
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from web_api.connectors.base import ErpAuthError
from web_api.connectors.billy import BillyConnector

FIXTURES = Path(__file__).parent / "fixtures" / "billy"
BASE_URL = "https://api.billysbilling.com/v2"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def paged(rows: list[dict], key: str, page: int, page_size: int) -> dict:
    """Wrap rows in Billy's list envelope for one page."""
    start = (page - 1) * page_size
    window = rows[start:start + page_size]
    page_count = max(1, -(-len(rows) // page_size))
    return {
        key: window,
        "meta": {"paging": {"page": page, "pageSize": page_size,
                            "pageCount": page_count, "total": len(rows)}},
    }


class Billy:
    """A stub Billy, recording what was asked of it."""

    def __init__(self, transactions=None, contacts=None, attachments=None):
        self.transactions = (transactions if transactions is not None
                             else load("transactions")["transactions"])
        self.contacts = (contacts if contacts is not None
                         else load("contacts_suppliers")["contacts"])
        self.attachments = (attachments if attachments is not None
                            else load("attachments")["attachments"])
        self.requests: list[httpx.Request] = []
        self.status_overrides: dict[str, int] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        params = request.url.params
        page = int(params.get("page", 1))
        size = int(params.get("pageSize", 100))

        for prefix, status in self.status_overrides.items():
            if path.startswith(prefix):
                return httpx.Response(status, text="denied")

        if path.endswith("/organization"):
            return httpx.Response(200, json=load("organization"))
        if path.endswith("/accounts"):
            return httpx.Response(200, json=paged(
                load("accounts")["accounts"], "accounts", page, size))
        if path.endswith("/contacts"):
            rows = self.contacts
            if params.get("isSupplier") == "true":
                rows = [c for c in rows if c.get("isSupplier")]
            return httpx.Response(200, json=paged(rows, "contacts", page, size))
        if path.endswith("/transactions"):
            rows = list(self.transactions)
            if params.get("sortProperty") == "entryDate":
                rows.sort(key=lambda r: r.get("entryDate") or "",
                          reverse=params.get("sortDirection") == "DESC")
            return httpx.Response(200, json=paged(rows, "transactions", page, size))
        if "/transactions/" in path:
            tid = path.rsplit("/", 1)[1]
            found = next((t for t in self.transactions if t["id"] == tid), None)
            if found is None:
                return httpx.Response(404, json={})
            return httpx.Response(200, json={"transaction": found})
        if "/bills/" in path:
            body = load("bill_single")
            if body["bill"]["id"] != path.rsplit("/", 1)[1]:
                return httpx.Response(404, json={})
            return httpx.Response(200, json=body)
        if path.endswith("/attachments"):
            return httpx.Response(200, json=paged(
                self.attachments, "attachments", page, size))
        if "/files/" in path:
            return httpx.Response(200, json=load("file"))
        if request.url.host.endswith("amazonaws.com"):
            return httpx.Response(200, content=b"%PDF-1.4 scrubbed")
        return httpx.Response(404, json={})

    def connector(self, handler=None, **config) -> BillyConnector:
        settings = {"access_token": "tok-live", "base_url": BASE_URL}
        settings.update(config)
        client = httpx.Client(
            transport=httpx.MockTransport(handler or self.handler), base_url=BASE_URL
        )
        return BillyConnector(settings, http_client=client)


@pytest.fixture
def billy():
    return Billy()


@pytest.fixture
def connector(billy):
    return billy.connector()


def test_every_request_carries_the_access_token(connector, billy):
    connector.fetch_accounts()
    assert billy.requests
    assert all(r.headers.get("X-Access-Token") == "tok-live" for r in billy.requests)


def test_authorize_discovers_the_organization_from_the_token(connector):
    assert connector._organization_id is None
    connector.authorize()
    assert connector._organization_id == load("organization")["organization"]["id"]


def test_a_supplied_organization_id_overrides_discovery(billy):
    connector = billy.connector(organization_id="chosen-org")
    connector.authorize()
    assert connector._organization_id == "chosen-org"
    assert not any(r.url.path.endswith("/organization") for r in billy.requests)


def test_a_revoked_token_is_an_auth_error(billy):
    billy.status_overrides["/v2/organization"] = 401
    with pytest.raises(ErpAuthError):
        billy.connector().authorize()


def test_test_connection_is_false_when_billy_is_unreachable(billy):
    def dead(request):
        raise httpx.ConnectError("unreachable", request=request)

    client = httpx.Client(transport=httpx.MockTransport(dead), base_url=BASE_URL)
    connector = BillyConnector({"access_token": "t", "base_url": BASE_URL}, http_client=client)
    assert connector.test_connection() is False


def test_accounts_map_from_the_real_chart(connector):
    accounts = connector.fetch_accounts()
    assert accounts
    by_code = {a.erp_account_code: a for a in accounts}
    raw = {str(r["accountNo"]): r for r in load("accounts")["accounts"]}

    for code, account in by_code.items():
        source = raw[code]
        assert account.is_active is not bool(source["isArchived"])
        assert account.with_vat is bool(source["taxRateId"])
        assert account.erp_account_type == source["natureId"]
        assert account.parent_code is None


def test_the_chart_covers_both_vat_settings(connector):
    assert {a.with_vat for a in connector.fetch_accounts()} == {True, False}


def test_an_archived_account_is_inactive(billy, monkeypatch):
    chart = load("accounts")
    assert not any(a["isArchived"] for a in chart["accounts"]), (
        "fixture now has an archived account; assert on it directly instead"
    )
    chart["accounts"][0]["isArchived"] = True
    target = str(chart["accounts"][0]["accountNo"])

    connector = billy.connector(
        lambda request: httpx.Response(200, json=chart)
        if request.url.path.endswith("/accounts")
        else billy.handler(request)
    )

    by_code = {a.erp_account_code: a for a in connector.fetch_accounts()}
    assert by_code[target].is_active is False


def test_only_suppliers_become_vendors(billy):
    connector = billy.connector()
    billy.contacts = load("contacts_all")["contacts"]
    customer_only = [c for c in billy.contacts
                     if c["isCustomer"] and not c["isSupplier"]]
    assert customer_only, "fixture must contain a customer-only contact"

    vendors = connector.fetch_vendors()

    assert {v.erp_id for v in vendors}.isdisjoint({c["id"] for c in customer_only})


def test_the_cvr_number_becomes_the_vendor_vat_number(connector):
    vendors = connector.fetch_vendors()
    source = {c["id"]: c for c in load("contacts_suppliers")["contacts"]}
    assert vendors
    for vendor in vendors:
        assert vendor.vat_number == source[vendor.erp_id]["registrationNo"]
        assert vendor.country_code == source[vendor.erp_id]["countryId"]


def test_postings_of_one_transaction_share_the_transaction_id_as_voucher(connector):
    entries = connector.fetch_entries()
    live = [t for t in load("transactions")["transactions"]
            if not t["isVoid"] and not t["isVoided"]
            and not t["originatorReference"].startswith("invoice:")]
    expected = {t["id"] for t in live}

    assert {e.voucher_id for e in entries} == expected


def test_the_blank_voucher_numbers_do_not_collide(connector):
    source = load("transactions")["transactions"]
    blank = [t for t in source if not t["voucherNo"]]
    assert len(blank) > 1, "fixture must contain several blank voucher numbers"

    entries = connector.fetch_entries()
    vouchers = {e.voucher_id for e in entries}
    live_blank = [t for t in blank
                  if not t["isVoid"] and not t["isVoided"]
                  and not t["originatorReference"].startswith("invoice:")]
    assert len({t["id"] for t in live_blank} & vouchers) == len(live_blank)


def test_no_entry_claims_an_invoice_line(connector):
    assert all(e.source_line_erp_id is None for e in connector.fetch_entries())


def test_a_posting_side_fills_exactly_one_amount(connector):
    entries = connector.fetch_entries()
    assert entries
    for entry in entries:
        assert (entry.debit_amount is None) != (entry.credit_amount is None)
    assert any(e.credit_amount is not None for e in entries)
    assert any(e.debit_amount is not None for e in entries)


def test_the_posting_account_id_becomes_an_account_number(connector):
    codes = {str(a["accountNo"]) for a in load("accounts")["accounts"]}
    entries = connector.fetch_entries()
    assert entries
    assert all(e.erp_account_code in codes for e in entries)


def test_a_posting_on_an_unknown_account_is_dropped(billy, caplog):
    transactions = [t for t in load("transactions")["transactions"]
                    if t["originatorReference"].startswith("daybookTransaction:")]
    assert transactions
    transactions[0]["postings"][0]["accountId"] = "no-such-account"
    billy.transactions = transactions

    entries = billy.connector().fetch_entries()

    assert len(entries) == len(transactions[0]["postings"]) - 1
    assert "unknown account" in caplog.text


def _type_for(connector, prefix: str) -> set[str]:
    return {e.entry_type for e in connector.fetch_entries()
            if e.voucher_id in {
                t["id"] for t in load("transactions")["transactions"]
                if t["originatorReference"].startswith(prefix)}}


@pytest.mark.parametrize("prefix,expected", [
    ("bill:", "purchase_invoice"),
    ("bankPayment:", "payment"),
    ("salesTaxPayment:", "payment"),
    ("daybookTransaction:", "journal_entry"),
    ("salesTaxReturn:", "journal_entry"),
])
def test_entry_type_per_originator_kind(connector, prefix, expected):
    assert _type_for(connector, prefix) == {expected}


def test_sales_invoices_are_not_returned(connector):
    sales = {t["id"] for t in load("transactions")["transactions"]
             if t["originatorReference"].startswith("invoice:")}
    assert sales, "fixture must contain a sales invoice"
    assert sales.isdisjoint({e.voucher_id for e in connector.fetch_entries()})


def test_the_originator_kind_is_read_from_the_reference_not_the_type_field(connector):
    source = load("transactions")["transactions"]
    assert all(t["originatorType"] is None for t in source)
    assert "purchase_invoice" in {e.entry_type for e in connector.fetch_entries()}


def test_an_unknown_originator_falls_back_and_is_logged_once(billy, caplog):
    transactions = [t for t in load("transactions")["transactions"]
                    if t["originatorReference"].startswith("daybookTransaction:")]
    for t in transactions:
        t["originatorReference"] = "quantumLedger:abc123"
    billy.transactions = transactions * 2

    entries = billy.connector().fetch_entries()

    assert entries and {e.entry_type for e in entries} == {"journal_entry"}
    assert caplog.text.count("quantumLedger") == 1


def test_neither_half_of_a_void_pair_yields_entries(connector):
    source = load("transactions")["transactions"]
    voided = {t["id"] for t in source if t["isVoid"] or t["isVoided"]}
    assert len(voided) >= 2, "fixture must contain a void pair"

    assert voided.isdisjoint({e.voucher_id for e in connector.fetch_entries()})


def test_a_bill_is_reachable_from_exactly_one_voucher(connector):
    entries = connector.fetch_entries()
    bill_ids = [connector._bill_id_by_voucher[v]
                for v in {e.voucher_id for e in entries}
                if v in connector._bill_id_by_voucher]
    assert bill_ids
    assert len(bill_ids) == len(set(bill_ids))


def test_since_stops_the_scan_and_returns_only_newer_entries(connector):
    cutoff = date(2026, 4, 21)
    entries = connector.fetch_entries(since=cutoff)
    assert entries
    assert all(e.accounting_date >= cutoff for e in entries)
    assert len(entries) < len(connector.fetch_entries())


def test_no_since_reads_the_whole_ledger(connector):
    assert connector.fetch_entries()


def test_the_scan_sorts_and_never_sends_a_date_filter(connector, billy):
    connector.fetch_entries(since=date(2026, 1, 1))

    tx_requests = [r for r in billy.requests if r.url.path.endswith("/transactions")]
    assert tx_requests
    for request in tx_requests:
        assert request.url.params.get("sortProperty") == "entryDate"
        assert request.url.params.get("sortDirection") == "DESC"
        for ignored in ("minEntryDate", "maxEntryDate", "entryDate", "period"):
            assert ignored not in request.url.params


def test_unselected_accounts_are_dropped(connector):
    chosen = connector.fetch_entries()[0].erp_account_code
    entries = connector.fetch_entries(account_codes={chosen})
    assert entries
    assert {e.erp_account_code for e in entries} == {chosen}


def test_an_empty_selection_issues_no_request(billy):
    connector = billy.connector()
    assert connector.fetch_entries(account_codes=set()) == []
    assert billy.requests == []


def _bill_voucher(connector) -> str:
    connector.fetch_entries()
    return next(iter(connector._bill_id_by_voucher))


def test_a_payment_voucher_has_no_scan(connector):
    entries = connector.fetch_entries()
    payment = next(e.voucher_id for e in entries if e.entry_type == "payment")
    assert connector.fetch_invoice_scan(payment) is None


def test_the_scan_reports_the_voucher_it_was_asked_for(connector):
    voucher = _bill_voucher(connector)
    scan = connector.fetch_invoice_scan(voucher)
    assert scan is not None
    assert scan.voucher_id == voucher


def test_a_blank_supplier_invoice_number_falls_back_to_the_bill_id(connector):
    bill = load("bill_single")["bill"]
    assert not bill["suppliersInvoiceNo"] and not bill["voucherNo"]

    scan = connector.fetch_invoice_scan(_bill_voucher(connector))
    assert scan.invoice_number == bill["id"]


def test_sideloaded_bill_lines_become_invoice_lines(connector):
    source = load("bill_single")
    scan = connector.fetch_invoice_scan(_bill_voucher(connector))
    codes = {str(a["id"]): str(a["accountNo"]) for a in load("accounts")["accounts"]}

    assert len(scan.lines) == len(source["billLines"])
    for line, raw in zip(scan.lines, source["billLines"]):
        assert line.line_erp_id == raw["id"]
        assert line.amount == raw["amount"]
        assert line.native_account_code == codes.get(raw["accountId"])


def test_a_bill_lines_text_names_the_item(connector):
    source = load("bill_single")
    scan = connector.fetch_invoice_scan(_bill_voucher(connector))

    for line, raw in zip(scan.lines, source["billLines"]):
        assert line.item_name == raw["description"]
        assert line.description is None


def test_the_scan_maps_the_money_from_the_bill(connector):
    bill = load("bill_single")["bill"]
    scan = connector.fetch_invoice_scan(_bill_voucher(connector))
    assert scan.total == bill["grossAmount"]
    assert scan.tax == bill["tax"]
    assert scan.currency == bill["currencyId"]
    assert scan.invoice_date == date.fromisoformat(bill["entryDate"])


def test_a_repeated_scan_lookup_issues_no_new_request(connector, billy):
    voucher = _bill_voucher(connector)
    connector.fetch_invoice_scan(voucher)
    before = len(billy.requests)
    connector.fetch_invoice_scan(voucher)
    assert len(billy.requests) == before


def test_the_scan_reports_the_attached_document(connector):
    attachment = load("attachments")["attachments"][0]
    scan = connector.fetch_invoice_scan(_bill_voucher(connector))
    assert scan.file_ref == attachment["fileId"]
    assert scan.file_name == load("file")["file"]["fileName"]


def test_an_unreadable_file_record_still_records_the_document(billy):
    billy.status_overrides["/v2/files/"] = 500

    connector = billy.connector()
    scan = connector.fetch_invoice_scan(_bill_voucher(connector))
    assert scan.file_ref == load("attachments")["attachments"][0]["fileId"]
    assert scan.file_name is None


def test_a_bill_with_no_attachment_reports_no_document(billy):
    billy.attachments = []
    connector = billy.connector()
    scan = connector.fetch_invoice_scan(_bill_voucher(connector))
    assert scan is not None
    assert scan.file_ref is None


def test_an_attachment_owned_by_something_other_than_this_bill_is_not_claimed(billy):
    attachment = dict(load("attachments")["attachments"][0])
    attachment["ownerReference"] = "invoice:some-other-id"
    billy.attachments = [attachment]

    connector = billy.connector()
    scan = connector.fetch_invoice_scan(_bill_voucher(connector))
    assert scan.file_ref is None


def test_the_lowest_priority_attachment_is_the_invoice(billy):
    primary = load("attachments")["attachments"][0]
    extra = dict(primary, id="extra", fileId="file-of-the-delivery-note", priority=9)
    billy.attachments = [extra, primary]

    connector = billy.connector()
    scan = connector.fetch_invoice_scan(_bill_voucher(connector))
    assert scan.file_ref == primary["fileId"]


def test_the_attachment_listing_is_fetched_once(connector, billy):
    voucher = _bill_voucher(connector)
    connector.fetch_invoice_scan(voucher)
    connector.fetch_invoice_document(voucher)

    listings = [r for r in billy.requests if r.url.path.endswith("/attachments")]
    assert len(listings) == 1
    files = [r for r in billy.requests if "/files/" in r.url.path]
    assert len(files) == 1


def test_the_document_is_fetched_without_our_credential(connector, billy):
    voucher = _bill_voucher(connector)
    payload = connector.fetch_invoice_document(voucher)

    assert payload is not None
    assert payload.content.startswith(b"%PDF-")
    assert payload.media_type == "application/pdf"
    assert payload.filename == load("file")["file"]["fileName"]

    download = next(r for r in billy.requests if r.url.host.endswith("amazonaws.com"))
    assert "X-Access-Token" not in download.headers


def test_an_image_attachment_keeps_its_own_media_type(billy):
    file_body = load("file")
    file_body["file"].update(fileName="receipt.png", fileType="png", isPdf=False)

    connector = billy.connector(
        lambda request: httpx.Response(200, json=file_body)
        if "/files/" in request.url.path
        else billy.handler(request)
    )

    payload = connector.fetch_invoice_document(_bill_voucher(connector))
    assert payload.media_type == "image/png"
    assert payload.filename == "receipt.png"


def test_the_supplier_name_is_resolved_from_the_contact(connector):
    assert load("bill_single")["bill"]["contactName"] is None

    scan = connector.fetch_invoice_scan(_bill_voucher(connector))
    contacts = {c["id"]: c["name"] for c in load("contacts_suppliers")["contacts"]}
    assert scan.vendor_name
    assert scan.vendor_name == contacts[scan.vendor_erp_id]


def test_a_voucher_with_no_attachment_has_no_document(billy):
    billy.attachments = []
    connector = billy.connector()
    assert connector.fetch_invoice_document(_bill_voucher(connector)) is None


def test_a_payment_voucher_has_no_document(connector):
    payment = next(e.voucher_id for e in connector.fetch_entries()
                   if e.entry_type == "payment")
    assert connector.fetch_invoice_document(payment) is None


def test_the_voided_transactions_are_reported_not_only_skipped(connector):
    source = load("transactions")["transactions"]
    voided = {t["id"] for t in source if t["isVoid"] or t["isVoided"]}

    connector.fetch_entries()

    assert connector.voided_voucher_ids() == voided


def test_voided_ids_describe_the_last_fetch_only(connector):
    connector.fetch_entries()
    first = connector.voided_voucher_ids()
    assert first

    connector.fetch_entries(account_codes=set())

    assert connector.voided_voucher_ids() == set()
