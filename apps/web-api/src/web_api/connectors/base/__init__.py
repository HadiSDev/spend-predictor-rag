"""The contract, payloads and errors shared by every ERP connector."""
from .connector import ErpConnector
from .credentials import CredentialField
from .documents import DocumentPayload
from .errors import ErpAuthError, ErpConnectionError, ErpDataError, ErpRateLimitError
from .invoices import ErpInvoiceData, ErpInvoiceLineData, ErpVendorData
from .ledger import ErpAccountData, ErpEntryData

__all__ = [
    "CredentialField",
    "DocumentPayload",
    "ErpAccountData",
    "ErpAuthError",
    "ErpConnectionError",
    "ErpConnector",
    "ErpDataError",
    "ErpEntryData",
    "ErpInvoiceData",
    "ErpInvoiceLineData",
    "ErpRateLimitError",
    "ErpVendorData",
]
