"""Billy (billy.dk) connector — Billy API v2.

Billy is a Danish SMB accounting system. Its ledger is transaction-centric: a
`transaction` is our voucher, its `postings` are our entries, and the supplier
`bill` a transaction originated from is our invoice scan.

Several mappings here contradict Billy's published documentation, and each one
was corrected by observing a real organization (see the design's "Resolved by
the spike"). The three that matter:

* The originator is a ``"kind:id"`` string in ``originatorReference``. The
  ``originatorType`` field the docs imply exists is null on every row.
* ``/transactions`` accepts ``minEntryDate`` and ignores it. The watermark is an
  early stop on an ``entryDate DESC`` scan instead.
* A document's ``downloadUrl`` is on S3 and *accepts* our access token, so the
  credential must be withheld deliberately — no failure would ever reveal it.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx

from . import register_connector
from .base import (
    CredentialField,
    DocumentPayload,
    ErpAccountData,
    ErpConnectionError,
    ErpConnector,
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

#: Originator kind (the prefix of ``originatorReference``) → our entry type.
#: A ``bill`` is resolved further: one that credits another bill is a credit
#: note. ``None`` means "not spend, do not return" — a sales invoice is revenue.
_ENTRY_TYPE_BY_ORIGINATOR: dict[str, str | None] = {
    "bill": "purchase_invoice",
    "bankPayment": "payment",
    "salesTaxPayment": "payment",
    "daybookTransaction": "journal_entry",
    "salesTaxReturn": "journal_entry",
    "invoice": None,
}

#: An originator we do not know still moved money through a selected account, so
#: it is kept rather than dropped — dropping it would understate spend.
_FALLBACK_ENTRY_TYPE = "journal_entry"

#: Billy's ``fileType`` → a media type a browser will render inline. Not every
#: attachment is a scan: customers attach phone photos and screenshots of a
#: receipt just as often, and serving those as ``application/octet-stream``
#: makes the browser download the file instead of showing it.
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
    """Connector for Billy API v2.

    Config:
        access_token: str    (required — Billy access token, bound to one org)
        organization_id: str (optional — discovered from the token if omitted)
        base_url: str        (optional, default https://api.billysbilling.com/v2)
    """

    display_label = "Billy"
    brand_slug = "billy"
    description = "Danish accounting for small and medium businesses."
    docs_url = "https://www.billy.dk/api"

    # Numbered pages; the row key differs per resource, so callers name it.
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
        # Optional: a token is bound to one organization, so `authorize()` can
        # discover it. Supplying it only overrides that.
        CredentialField(name="organization_id", label="Organization ID"),
        CredentialField(name="base_url", label="API base URL", default=DEFAULT_BASE_URL),
    ]

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.access_token = config.get("access_token") or ""
        self.base_url = config.get("base_url") or DEFAULT_BASE_URL
        self._organization_id: str | None = config.get("organization_id") or None
        #: accountId → accountNo. Postings and bill lines both name their account
        #: by id, while everything downstream keys on the number.
        self._account_no_by_id: dict[str, str] = {}
        #: voucher ids the last fetch saw Billy mark voided (see
        #: ``voided_voucher_ids``); cleared at the start of every fetch so it
        #: never reports a voucher this run did not look at.
        self._voided_voucher_ids: set[str] = set()
        #: transaction id → the bill id it originated from, built while fetching
        #: entries so `fetch_invoice_scan` needs no extra lookup.
        self._bill_id_by_voucher: dict[str, str] = {}
        self._bill_cache: dict[str, ErpInvoiceData | None] = {}
        #: contactId → name. A real bill carries `contactName: null` and only
        #: the id, so the supplier's name has to come from the contact record.
        self._contact_name_by_id: dict[str, str] = {}
        #: bill id → its attachment record, built on first use. `None` until
        #: then, so "no attachments in this organization" is distinguishable
        #: from "not asked yet" and the listing is never fetched twice.
        self._attachment_index: dict[str, dict] | None = None
        #: fileId → Billy's file record. Both the scan (for the name) and the
        #: document route (for the URL and media type) want the same record.
        self._file_cache: dict[str, dict] = {}
        #: Unrecognised originator kinds already logged, so a novel kind is one
        #: log line per sync rather than one per posting.
        self._logged_unknown: set[str] = set()

    # -- HTTP seams ----------------------------------------------------------

    def _base_url(self) -> str:
        return self.base_url

    def _auth_headers(self) -> dict[str, str]:
        return {"X-Access-Token": self.access_token}

    def _org_params(self) -> dict[str, str]:
        """Scope a list request to the token's organization, when known."""
        return {"organizationId": self._organization_id} if self._organization_id else {}

    # -- Connector interface -------------------------------------------------

    def authorize(self) -> str:
        """Verify the token and learn which organization it is bound to.

        A Billy token belongs to exactly one organization, so asking Billy is
        more reliable than asking the user — and it keeps the connect form to
        the single field a customer has to go and find.
        """
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
                    # `natureId` is itself the semantic string — "expense",
                    # "asset", "liability", "revenue", "equity" — so the type
                    # needs neither a sideload nor a second request.
                    erp_account_type=r.get("natureId"),
                    # Billy account *groups* are not accounts, so asserting one
                    # as a parent would invent a chart level that does not exist.
                    parent_code=None,
                    is_active=not r.get("isArchived", False),
                    # The ERP's value seeds the customer setting once; from then
                    # on neither refresh nor sync may overwrite it.
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
        """A supplier's name, fetching the contact book once if it is cold.

        Bills name their supplier by id and leave `contactName` null, so without
        this an invoice would be written with a blank vendor name. The runner
        calls `fetch_vendors()` before any scan, so the lazy fetch is a
        safety net for a connector used directly rather than the normal path.
        """
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
                # The CVR number in Denmark, which is what the runner's vendor
                # identity rule prefers over a name.
                vat_number=r.get("registrationNo") or r.get("vatNo"),
                raw=r,
            )
            for r in rows
            # Belt and braces: the filter is server-side, but a customer contact
            # must never become a supplier if Billy ever ignores it.
            if r.get("isSupplier")
        ]

    def _attachments_by_bill(self) -> dict[str, dict]:
        """Bill id → the attachment record holding its scanned document.

        ``/attachments`` is an org-wide listing with no per-owner filter, so
        asking for one bill's attachment costs exactly what asking for all of
        them costs — hence one fetch per connector, shared by both callers.

        Both need it. The scan records *that* a document exists, which is what
        makes the runner write a ``File`` row; without one, the document
        endpoint refuses before it ever asks the ERP. The document route needs
        the file id it points at.
        """
        if self._attachment_index is None:
            rows = self._paginate(
                "/attachments", items_key="attachments", **self._org_params()
            )
            index: dict[str, dict] = {}
            # A bill can carry several attachments — a second page, a delivery
            # note, a receipt. `priority` is Billy's own ordering of them, so
            # the lowest is the one a person would call "the invoice".
            for attachment in sorted(rows, key=lambda r: r.get("priority") or 0):
                reference = str(attachment.get("ownerReference") or "")
                kind, _, owner_id = reference.partition(":")
                if kind == "bill" and owner_id and attachment.get("fileId"):
                    index.setdefault(owner_id, attachment)
            self._attachment_index = index
        return self._attachment_index

    def _file_record(self, file_id: str) -> dict:
        """Billy's record for one file: its name, type and download URL.

        Memoised because both callers want the same record for the same file —
        the scan takes the name, the document route takes the URL and the media
        type — and a file is never asked for twice within one connector.
        """
        if file_id not in self._file_cache:
            body = self._get(f"/files/{file_id}")
            # A by-id fetch returns `file` singular; a list returns `files`.
            self._file_cache[file_id] = (
                body.get("file") or (body.get("files") or [None])[0] or {}
            )
        return self._file_cache[file_id]

    def fetch_invoices(self, since: date | None = None) -> list[ErpInvoiceData]:
        """Supplier bills in their own right, independent of the ledger.

        The sync runner does not use this — it walks vouchers and pulls each
        one's scan — but the interface requires it, and it is the honest
        implementation: `/bills` is one of the few Billy listings whose
        `minEntryDate` filter actually works, so this one *is* bounded
        server-side.

        A bill reached this way carries no `voucher_id` unless a previous
        `fetch_entries` happened to learn it: the transaction is what knows
        which bill it posted, not the other way round.
        """
        self._ensure_accounts()
        params: dict[str, Any] = {}
        if since:
            params["minEntryDate"] = since.isoformat()

        # Paged here rather than through `_paginate` because lines sideload
        # *beside* the bills, and both keys have to be collected together.
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

    # -- Entries -------------------------------------------------------------

    @staticmethod
    def _split_originator(transaction: dict) -> tuple[str | None, str | None]:
        """``("bill", "<id>")`` from ``originatorReference``.

        Read from the reference string, never from ``originatorType``: Billy
        leaves that null, so trusting it would send every transaction to the
        fallback type.
        """
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
        """Transactions newest-first, stopping once they predate ``since``.

        Billy accepts ``minEntryDate`` on this endpoint and **ignores it** — a
        future lower bound returns the whole ledger — so a filter here would
        quietly re-fetch everything on every sync. Sorting *is* honoured, so the
        watermark is an early stop instead.
        """
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
                    # This page crossed the watermark; everything after it is
                    # older still, so there is nothing left to ask for.
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
        """A row's entry date, or the minimum date when it has none.

        Undated rows sort as oldest, which for the early stop means "do not let
        a missing date look newer than the watermark and keep the scan going".
        """
        raw = row.get("entryDate")
        return date.fromisoformat(raw) if raw else date.min

    def fetch_entries(
        self, since: date | None = None, account_codes: set[str] | None = None
    ) -> list[ErpEntryData]:
        # Reset before the early return, not after it: `voided_voucher_ids`
        # describes *this* fetch, and a caller acting on the previous fetch's
        # set would withdraw postings on the strength of a scan that never ran.
        self._voided_voucher_ids.clear()

        # An empty selection means "no accounts chosen" — nothing to ask for.
        if account_codes is not None and len(account_codes) == 0:
            return []

        self._ensure_accounts()
        entries: list[ErpEntryData] = []

        for transaction in self._transactions_since(since):
            # Billy voids by keeping the original (isVoided) and adding a
            # reversal (isVoid). Skipping both leaves every total unchanged —
            # the pair nets to zero — and keeps a bill reachable from exactly
            # one voucher, which the invoice join depends on.
            #
            # Recorded as well as skipped: a transaction voided *after* we
            # synced it would otherwise keep the postings we already stored, and
            # since Billy re-books the same bill under a new transaction, the
            # bill ends up under two vouchers with its spend counted twice.
            if transaction.get("isVoid") or transaction.get("isVoided"):
                self._voided_voucher_ids.add(str(transaction["id"]))
                continue

            entry_type = self._entry_type(transaction)
            if entry_type is None:
                continue  # a sales invoice: revenue, not spend

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
            # Storing a blank code would pollute every per-account total and
            # make the row unfilterable, which is worse than losing it loudly.
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
            # A Billy posting references its transaction, never a bill line, so
            # there is no line to name. Inferring one by matching account and
            # amount would put a guessed category on a real posting.
            source_line_erp_id=None,
            accounting_date=date.fromisoformat(accounting_date) if accounting_date else None,
            description=posting.get("text") or transaction.get("originatorName"),
            debit_amount=amount if side == "debit" else None,
            credit_amount=amount if side == "credit" else None,
            currency=posting.get("currencyId"),
            raw=posting,
        )

    # -- Invoice scans -------------------------------------------------------

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
            # A payment or a journal entry has no scan. Ordinary, not an error.
            self._bill_cache[voucher_id] = None
            return None

        self._ensure_accounts()
        body = self._get(f"/bills/{bill_id}", include="bill.lines")
        # A by-id fetch returns `bill` singular; a list returns `bills`.
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
                description=line.get("description") or "",
                quantity=line.get("quantity"),
                unit_price=None,  # Billy states an amount, not a unit price.
                amount=float(line.get("amount") or 0),
                native_account_code=self._account_no_by_id.get(
                    str(line.get("accountId") or "")
                ),
                raw=line,
            )
            # Lines sideload beside the bill rather than nesting inside it.
            for line in all_lines
            if str(line.get("billId") or "") == bill_id
        ]

        # `suppliersInvoiceNo` is user-entered and often blank, and `voucherNo`
        # is blank at least as often — the first real bill observed had neither,
        # so the bill id is a load-bearing fallback, not a formality.
        invoice_number = bill.get("suppliersInvoiceNo") or bill.get("voucherNo") or bill_id

        # The attachment is what tells the runner to write a `File` row, and the
        # `File` row is what the document endpoint gates on. The attachment
        # names no file, so the name costs one lookup — worth it, because it is
        # the name the customer sees and downloads under, and "scan.pdf" (the
        # runner's placeholder) is an outright lie for the phone photo of a
        # receipt that a fair share of Billy attachments turn out to be.
        attachment = self._attachments_by_bill().get(bill_id)
        file_name = None
        if attachment is not None:
            try:
                file_name = self._file_record(str(attachment["fileId"])).get("fileName")
            except (ErpConnectionError, ErpDataError):
                # A name is not worth failing a whole sync over: the ledger data
                # still lands, and the document route resolves the record again
                # when someone actually opens the file.
                logger.warning(
                    "Billy file %s (bill %s) could not be read; storing it unnamed",
                    attachment.get("fileId"), bill_id,
                )

        return ErpInvoiceData(
            erp_id=bill_id,
            vendor_erp_id=str(bill.get("contactId") or ""),
            # `contactName` is null on real bills, so the id is the only route
            # to the supplier's name — and a blank one would land in the ledger.
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

    # -- Documents -----------------------------------------------------------

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
            # The download carries no content-disposition, so the name has to
            # come from the file record rather than from the response.
            filename=file.get("fileName") or f"voucher_{voucher_id}",
        )

    def voided_voucher_ids(self) -> set[str]:
        return set(self._voided_voucher_ids)

    def _download(self, url: str) -> bytes | None:
        """Fetch a document, withholding our credential from a foreign host.

        Billy stores documents on object storage that *accepts* the access token
        rather than rejecting it, so sending it would work — and nothing would
        ever fail in a way that revealed we were handing a Billy credential to a
        third party. Hence an explicit host check rather than a fallback.
        """
        same_host = httpx.URL(url).host == httpx.URL(self.base_url).host
        result = self._request_raw(url, authenticated=same_host)
        return None if result is None else result[0]


register_connector("billy", BillyConnector)
