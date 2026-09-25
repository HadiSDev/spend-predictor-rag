"""Mock ERP connector — calls the mock-erp-api FastAPI server."""
from __future__ import annotations

from datetime import date
from typing import Any

from .base import (
    CredentialField,
    DocumentPayload,
    ErpAccountData,
    ErpConnectionError,
    ErpEntryData,
    ErpInvoiceData,
    ErpInvoiceLineData,
    ErpVendorData,
)
from .http import HttpErpConnector
from .pagination import PageNumberPaginator

DEFAULT_BASE_URL = "http://localhost:8001"
DEFAULT_API_KEY = "mock-secret"


class MockErpConnector(HttpErpConnector):
    """Connector that talks to the mock-erp-api server."""

    display_label = "Debug ERP"
    brand_slug = "mock"
    description = "A local fake ERP for development and demos."
    paginator = PageNumberPaginator(
        items_key="collection",
        total_path=("pagination", "total"),
        page_param="page",
        size_param="pageSize",
        page_size=100,
        first_page=1,
    )
    credential_fields = [
        CredentialField(name="base_url", label="Base URL", default=DEFAULT_BASE_URL),
        CredentialField(name="api_key", label="API key", secret=True, default=DEFAULT_API_KEY),
    ]

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.base_url = config.get("base_url") or DEFAULT_BASE_URL
        self.api_key = config.get("api_key") or DEFAULT_API_KEY
        self._token: str | None = None
        self._invoice_by_voucher: dict[str, dict] | None = None

    def _base_url(self) -> str:
        return self.base_url

    def _auth_headers(self) -> dict[str, str]:
        return {"x-app-secret-token": self.api_key}

    def authorize(self) -> str:
        self._token = self.api_key
        return self._token

    def test_connection(self) -> bool:
        try:
            body = self._get("/api/v1/health")
            return body.get("status") == "ok"
        except ErpConnectionError:
            return False

    def fetch_accounts(self) -> list[ErpAccountData]:
        raw_list = self._paginate("/api/v1/accounts")
        return [
            ErpAccountData(
                erp_account_code=str(r["accountNumber"]),
                erp_account_name=r["name"],
                erp_account_type=r.get("accountType"),
                parent_code=str(r["parentAccountNumber"]) if r.get("parentAccountNumber") else None,
                is_active=r.get("isActive", True),
                with_vat=r.get("withVat", False),
                raw=r,
            )
            for r in raw_list
        ]

    def fetch_vendors(self, since: date | None = None) -> list[ErpVendorData]:
        raw_list = self._paginate("/api/v1/vendors")
        return [
            ErpVendorData(
                erp_id=str(r["vendorNumber"]),
                name=r["name"],
                country_code=r.get("country"),
                vat_number=r.get("vatNumber"),
                raw=r,
            )
            for r in raw_list
        ]

    @staticmethod
    def _map_invoice(r: dict) -> ErpInvoiceData:
        lines = [
            ErpInvoiceLineData(
                line_erp_id=str(ln.get("lineNumber", "")),
                item_name=ln.get("description") or None,
                quantity=ln.get("quantity"),
                unit_price=ln.get("unitPrice"),
                amount=ln.get("netAmount", 0),
                native_account_code=str(ln.get("account", {}).get("accountNumber", "")),
                raw=ln,
            )
            for ln in r.get("lines", [])
        ]
        file = r.get("file", {}) or {}
        voucher = r.get("voucherId")
        return ErpInvoiceData(
            erp_id=str(r["purchaseInvoiceNumber"]),
            vendor_erp_id=str(r.get("supplier", {}).get("supplierNumber", "")),
            vendor_name=r.get("supplier", {}).get("name", ""),
            invoice_number=str(r.get("purchaseInvoiceNumber", "")),
            invoice_date=date.fromisoformat(r["date"]),
            currency=r.get("currency", "DKK"),
            total=float(r.get("grossAmount", 0)),
            tax=float(r.get("vatAmount")) if r.get("vatAmount") else None,
            voucher_id=str(voucher) if voucher is not None else None,
            file_name=file.get("fileName"),
            file_ref=file.get("fileRef"),
            lines=lines,
            raw=r,
        )

    def fetch_invoices(self, since: date | None = None) -> list[ErpInvoiceData]:
        params: dict[str, Any] = {}
        if since:
            params["since"] = since.isoformat()
        raw_list = self._paginate("/api/v1/purchase-invoices", **params)
        return [self._map_invoice(r) for r in raw_list]

    def fetch_entries(
        self, since: date | None = None, account_codes: set[str] | None = None
    ) -> list[ErpEntryData]:
        if account_codes is not None and len(account_codes) == 0:
            return []
        params: dict[str, Any] = {}
        if since:
            params["since"] = since.isoformat()
        if account_codes is not None:
            params["accounts"] = ",".join(sorted(account_codes))
        raw_list = self._paginate("/api/v1/entries", **params)
        result: list[ErpEntryData] = []
        for r in raw_list:
            accounting_date = r.get("date")
            result.append(
                ErpEntryData(
                    erp_entry_id=str(r["entryNumber"]),
                    voucher_id=str(r["voucherId"]),
                    entry_type=r.get("entryType", "journal_entry"),
                    erp_account_code=str(r.get("account", {}).get("accountNumber", "")),
                    accounting_date=date.fromisoformat(accounting_date) if accounting_date else None,
                    source_line_erp_id=(
                        str(r["lineNumber"]) if r.get("lineNumber") is not None else None
                    ),
                    description=r.get("description"),
                    debit_amount=r.get("debit"),
                    credit_amount=r.get("credit"),
                    currency=r.get("currency"),
                    raw=r,
                )
            )
        return result

    def fetch_invoice_scan(self, voucher_id: str) -> ErpInvoiceData | None:
        """Return the invoice scan for a voucher, or None if it has no scan."""
        if self._invoice_by_voucher is None:
            raw_list = self._paginate("/api/v1/purchase-invoices")
            self._invoice_by_voucher = {
                str(r["voucherId"]): r
                for r in raw_list
                if r.get("voucherId") is not None
            }
        raw = self._invoice_by_voucher.get(str(voucher_id))
        return self._map_invoice(raw) if raw is not None else None

    def fetch_invoice_document(self, voucher_id: str) -> DocumentPayload | None:
        """Fetch the voucher's PDF from the mock ERP's document endpoint."""
        response = self._request_raw(f"/api/v1/documents/{voucher_id}")
        if response is None:
            return None
        content, filename = response
        return DocumentPayload(
            content=content,
            media_type="application/pdf",
            filename=filename or f"voucher_{voucher_id}.pdf",
        )
