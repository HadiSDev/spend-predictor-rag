"""Billy (billy.dk) connector — Billy API v2."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx

from .base import (
    CredentialField,
    DocumentPayload,
    ErpAccountData,
    ErpConnectionError,
    ErpDataError,
    ErpEntryData,
    ErpInvoiceData,
    ErpInvoiceLineData,
    ErpVendorData,
)
from .http import HttpErpConnector
from .pagination import PageNumberPaginator

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.billysbilling.com/v2"

_ENTRY_TYPE_BY_ORIGINATOR: dict[str, str | None] = {
    "bill": "purchase_invoice",
    "bankPayment": "payment",
    "salesTaxPayment": "payment",
    "daybookTransaction": "journal_entry",
    "salesTaxReturn": "journal_entry",
    "invoice": None,
}

_FALLBACK_ENTRY_TYPE = "journal_entry"

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
}


def _media_type(file: dict) -> str:
    """The media type for a Billy file record."""
    file_type = str(file.get("fileType") or "").lower().lstrip(".")
    if file_type in _MEDIA_TYPES:
        return _MEDIA_TYPES[file_type]
    if file.get("isPdf"):
        return "application/pdf"
    return "application/octet-stream"


class BillyConnector(HttpErpConnector):
    """Connector for Billy API v2."""

    display_label = "Billy"
    brand_slug = "billy"
    description = "Danish accounting for small and medium businesses."
    docs_url = "https://www.billy.dk/api"

    paginator = PageNumberPaginator(
        total_path=("meta", "paging", "total"),
        page_param="page",
        size_param="pageSize",
        page_size=100,
        first_page=1,
    )

    credential_fields = [
        CredentialField(
            name="access_token", label="Access token", required=True, secret=True
        ),
        CredentialField(name="organization_id", label="Organization ID"),
        CredentialField(name="base_url", label="API base URL", default=DEFAULT_BASE_URL),
    ]

    def __init__(self, config: dict, http_client: httpx.Client | None = None) -> None:
        super().__init__(config, http_client)
        self.access_token = config.get("access_token") or ""
        self.base_url = config.get("base_url") or DEFAULT_BASE_URL
        self._organization_id: str | None = config.get("organization_id") or None
        self._account_no_by_id: dict[str, str] = {}
        self._voided_voucher_ids: set[str] = set()
        self._bill_id_by_voucher: dict[str, str] = {}
        self._bill_cache: dict[str, ErpInvoiceData | None] = {}
        self._contact_name_by_id: dict[str, str] = {}
        self._attachment_index: dict[str, dict] | None = None
        self._file_cache: dict[str, dict] = {}
        self._logged_unknown: set[str] = set()

    def _base_url(self) -> str:
        return self.base_url

    def _auth_headers(self) -> dict[str, str]:
        return {"X-Access-Token": self.access_token}

    def _org_params(self) -> dict[str, str]:
        """Scope a list request to the token's organization, when known."""
        return {"organizationId": self._organization_id} if self._organization_id else {}

    def authorize(self) -> str:
        """Verify the token and learn which organization it is bound to."""
        if not self._organization_id:
            body = self._get("/organization")
            org = body.get("organization") or {}
            self._organization_id = org.get("id")
        return self.access_token

    def test_connection(self) -> bool:
        try:
            body = self._get("/organization")
        except ErpConnectionError:
            return False
        return bool((body.get("organization") or {}).get("id"))

    def fetch_accounts(self) -> list[ErpAccountData]:
        rows = self._paginate("/accounts", items_key="accounts", **self._org_params())
        accounts: list[ErpAccountData] = []
        for r in rows:
            code = str(r.get("accountNo") or "")
            if r.get("id") and code:
                self._account_no_by_id[str(r["id"])] = code
            accounts.append(
                ErpAccountData(
                    erp_account_code=code,
                    erp_account_name=r.get("name") or "",
                    erp_account_type=r.get("natureId"),
                    parent_code=None,
                    is_active=not r.get("isArchived", False),
                    with_vat=bool(r.get("taxRateId")),
                    raw=r,
                )
            )
        return accounts

    def _ensure_accounts(self) -> None:
        """Make sure the accountId → accountNo map is populated."""
        if not self._account_no_by_id:
            self.fetch_accounts()

    def _contact_name(self, contact_id: str) -> str:
        """A supplier's name, fetching the contact book once if it is cold."""
        if not contact_id:
            return ""
        if contact_id not in self._contact_name_by_id:
            self.fetch_vendors()
        return self._contact_name_by_id.get(contact_id, "")

    def fetch_vendors(self, since: date | None = None) -> list[ErpVendorData]:
        rows = self._paginate(
            "/contacts", items_key="contacts", isSupplier="true", **self._org_params()
        )
        for r in rows:
            if r.get("id") and r.get("name"):
                self._contact_name_by_id[str(r["id"])] = r["name"]
        return [
            ErpVendorData(
                erp_id=str(r["id"]),
                name=r.get("name") or "",
                country_code=r.get("countryId"),
                vat_number=r.get("registrationNo") or r.get("vatNo"),
                raw=r,
            )
            for r in rows
            if r.get("isSupplier")
        ]

    def _attachments_by_bill(self) -> dict[str, dict]:
        """Bill id → the attachment record holding its scanned document."""
        if self._attachment_index is None:
            rows = self._paginate(
                "/attachments", items_key="attachments", **self._org_params()
            )
            index: dict[str, dict] = {}
            for attachment in sorted(rows, key=lambda r: r.get("priority") or 0):
                reference = str(attachment.get("ownerReference") or "")
                kind, _, owner_id = reference.partition(":")
                if kind == "bill" and owner_id and attachment.get("fileId"):
                    index.setdefault(owner_id, attachment)
            self._attachment_index = index
        return self._attachment_index

    def _file_record(self, file_id: str) -> dict:
        """Billy's record for one file: its name, type and download URL."""
        if file_id not in self._file_cache:
            body = self._get(f"/files/{file_id}")
            self._file_cache[file_id] = (
                body.get("file") or (body.get("files") or [None])[0] or {}
            )
        return self._file_cache[file_id]

    def fetch_invoices(self, since: date | None = None) -> list[ErpInvoiceData]:
        """Supplier bills in their own right, independent of the ledger."""
        self._ensure_accounts()
        params: dict[str, Any] = {}
        if since:
            params["minEntryDate"] = since.isoformat()

        bills: list[dict] = []
        lines: list[dict] = []
        page = 1
        while True:
            body = self._get(
                "/bills", page=page, pageSize=self.paginator.page_size,
                include="bill.lines", **params, **self._org_params(),
            )
            bills.extend(body.get("bills") or [])
            lines.extend(body.get("billLines") or [])
            paging = (body.get("meta") or {}).get("paging") or {}
            if page >= (paging.get("pageCount") or 1):
                break
            page += 1

        voucher_by_bill = {b: v for v, b in self._bill_id_by_voucher.items()}
        return [
            self._map_bill(bill, lines, voucher_by_bill.get(str(bill["id"])))
            for bill in bills
        ]

    @staticmethod
    def _split_originator(transaction: dict) -> tuple[str | None, str | None]:
        """``("bill", "<id>")`` from ``originatorReference``."""
        reference = transaction.get("originatorReference")
        if not reference or ":" not in str(reference):
            return None, None
        kind, _, originator_id = str(reference).partition(":")
        return kind or None, originator_id or None

    def _entry_type(self, transaction: dict) -> str | None:
        """Our entry type for a transaction, or ``None`` to skip it entirely."""
        kind, _ = self._split_originator(transaction)
        if kind is None:
            return _FALLBACK_ENTRY_TYPE
        if kind not in _ENTRY_TYPE_BY_ORIGINATOR:
            if kind not in self._logged_unknown:
                self._logged_unknown.add(kind)
                logger.warning(
                    "Billy originator %r is not mapped; treating its postings as %s",
                    kind, _FALLBACK_ENTRY_TYPE,
                )
            return _FALLBACK_ENTRY_TYPE
        entry_type = _ENTRY_TYPE_BY_ORIGINATOR[kind]
        return entry_type

    def _transactions_since(self, since: date | None) -> list[dict]:
        """Transactions newest-first, stopping once they predate ``since``."""
        collected: list[dict] = []
        page = 1
        while True:
            body = self._get(
                "/transactions",
                page=page,
                pageSize=self.paginator.page_size,
                sortProperty="entryDate",
                sortDirection="DESC",
                include="transaction.postings:embed",
                **self._org_params(),
            )
            rows = body.get("transactions") or []
            if not rows:
                break

            if since is not None:
                keep = [r for r in rows if self._entry_date(r) >= since]
                collected.extend(keep)
                if len(keep) < len(rows):
                    break
            else:
                collected.extend(rows)

            paging = (body.get("meta") or {}).get("paging") or {}
            if page >= (paging.get("pageCount") or 1):
                break
            page += 1
        return collected

    @staticmethod
    def _entry_date(row: dict) -> date:
        """A row's entry date, or the minimum date when it has none."""
        raw = row.get("entryDate")
        return date.fromisoformat(raw) if raw else date.min

    def fetch_entries(
        self, since: date | None = None, account_codes: set[str] | None = None
    ) -> list[ErpEntryData]:
        self._voided_voucher_ids.clear()

        if account_codes is not None and len(account_codes) == 0:
            return []

        self._ensure_accounts()
        entries: list[ErpEntryData] = []

        for transaction in self._transactions_since(since):
            if transaction.get("isVoid") or transaction.get("isVoided"):
                self._voided_voucher_ids.add(str(transaction["id"]))
                continue

            entry_type = self._entry_type(transaction)
            if entry_type is None:
                continue

            voucher_id = str(transaction["id"])
            kind, originator_id = self._split_originator(transaction)
            if kind == "bill" and originator_id:
                self._bill_id_by_voucher[voucher_id] = originator_id

            for posting in transaction.get("postings") or []:
                entry = self._map_posting(posting, transaction, voucher_id, entry_type)
                if entry is None:
                    continue
                if account_codes is not None and entry.erp_account_code not in account_codes:
                    continue
                entries.append(entry)

        return entries

    def _map_posting(
        self, posting: dict, transaction: dict, voucher_id: str, entry_type: str
    ) -> ErpEntryData | None:
        """One posting as an entry, or ``None`` if its account is unknown."""
        account_id = str(posting.get("accountId") or "")
        code = self._account_no_by_id.get(account_id)
        if not code:
            logger.warning(
                "Billy posting %s names unknown account %s; skipping it",
                posting.get("id"), account_id,
            )
            return None

        amount = posting.get("amount")
        side = (posting.get("side") or "").lower()
        accounting_date = posting.get("entryDate") or transaction.get("entryDate")

        return ErpEntryData(
            erp_entry_id=str(posting["id"]),
            voucher_id=voucher_id,
            entry_type=entry_type,
            erp_account_code=code,
            source_line_erp_id=None,
            accounting_date=date.fromisoformat(accounting_date) if accounting_date else None,
            description=posting.get("text") or transaction.get("originatorName"),
            debit_amount=amount if side == "debit" else None,
            credit_amount=amount if side == "credit" else None,
            currency=posting.get("currencyId"),
            raw=posting,
        )

    def _bill_id_for(self, voucher_id: str) -> str | None:
        """The bill a voucher originated from, fetching the voucher if needed."""
        known = self._bill_id_by_voucher.get(str(voucher_id))
        if known:
            return known
        try:
            body = self._get(f"/transactions/{voucher_id}")
        except ErpDataError:
            return None
        transaction = body.get("transaction") or {}
        kind, originator_id = self._split_originator(transaction)
        if kind != "bill" or not originator_id:
            return None
        self._bill_id_by_voucher[str(voucher_id)] = originator_id
        return originator_id

    def fetch_invoice_scan(self, voucher_id: str) -> ErpInvoiceData | None:
        voucher_id = str(voucher_id)
        if voucher_id in self._bill_cache:
            return self._bill_cache[voucher_id]

        bill_id = self._bill_id_for(voucher_id)
        if bill_id is None:
            self._bill_cache[voucher_id] = None
            return None

        self._ensure_accounts()
        body = self._get(f"/bills/{bill_id}", include="bill.lines")
        bill = body.get("bill") or (body.get("bills") or [None])[0]
        if bill is None:
            self._bill_cache[voucher_id] = None
            return None

        scan = self._map_bill(bill, body.get("billLines") or [], voucher_id)
        self._bill_cache[voucher_id] = scan
        return scan

    def _map_bill(
        self, bill: dict, all_lines: list[dict], voucher_id: str | None
    ) -> ErpInvoiceData:
        bill_id = str(bill["id"])
        lines = [
            ErpInvoiceLineData(
                line_erp_id=str(line["id"]),
                item_name=line.get("description") or None,
                quantity=line.get("quantity"),
                unit_price=None,
                amount=float(line.get("amount") or 0),
                native_account_code=self._account_no_by_id.get(
                    str(line.get("accountId") or "")
                ),
                raw=line,
            )
            for line in all_lines
            if str(line.get("billId") or "") == bill_id
        ]

        invoice_number = bill.get("suppliersInvoiceNo") or bill.get("voucherNo") or bill_id

        attachment = self._attachments_by_bill().get(bill_id)
        file_name = None
        if attachment is not None:
            try:
                file_name = self._file_record(str(attachment["fileId"])).get("fileName")
            except (ErpConnectionError, ErpDataError):
                logger.warning(
                    "Billy file %s (bill %s) could not be read; storing it unnamed",
                    attachment.get("fileId"), bill_id,
                )

        return ErpInvoiceData(
            erp_id=bill_id,
            vendor_erp_id=str(bill.get("contactId") or ""),
            vendor_name=bill.get("contactName")
            or self._contact_name(str(bill.get("contactId") or "")),
            invoice_number=str(invoice_number),
            invoice_date=date.fromisoformat(bill["entryDate"]),
            currency=bill.get("currencyId") or "DKK",
            total=float(bill.get("grossAmount") or bill.get("amount") or 0),
            tax=float(bill["tax"]) if bill.get("tax") is not None else None,
            voucher_id=voucher_id,
            file_ref=str(attachment["fileId"]) if attachment else None,
            file_name=file_name,
            lines=lines,
            raw=bill,
        )

    def fetch_invoice_document(self, voucher_id: str) -> DocumentPayload | None:
        bill_id = self._bill_id_for(str(voucher_id))
        if bill_id is None:
            return None

        attachment = self._attachments_by_bill().get(bill_id)
        if attachment is None:
            return None

        file = self._file_record(str(attachment["fileId"]))
        url = file.get("downloadUrl")
        if not url:
            return None

        content = self._download(url)
        if content is None:
            return None
        return DocumentPayload(
            content=content,
            media_type=_media_type(file),
            filename=file.get("fileName") or f"voucher_{voucher_id}",
        )

    def voided_voucher_ids(self) -> set[str]:
        return set(self._voided_voucher_ids)

    def _download(self, url: str) -> bytes | None:
        """Fetch a document, withholding our credential from a foreign host."""
        same_host = httpx.URL(url).host == httpx.URL(self.base_url).host
        result = self._request_raw(url, authenticated=same_host)
        return None if result is None else result[0]
