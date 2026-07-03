"""Pydantic response models for the mock ERP API."""

from datetime import date
from typing import Any

from pydantic import BaseModel


class Pagination(BaseModel):
    maxPageSize: int = 20
    page: int = 1
    results: int = 0
    total: int = 0


class PaginatedResponse(BaseModel):
    collection: list[dict] = []
    pagination: Pagination = Pagination()


class AccountResponse(BaseModel):
    accountNumber: int
    name: str
    accountType: str
    parentAccountNumber: int | None = None
    isActive: bool = True
    withVat: bool = False
    balance: float = 0.0


class VendorResponse(BaseModel):
    vendorNumber: int
    name: str
    country: str = "DK"
    vatNumber: str = ""
    currency: str = "DKK"
    supplierGroup: dict = {}


class InvoiceLineResponse(BaseModel):
    lineNumber: int
    description: str
    quantity: float | None = None
    unitPrice: float | None = None
    netAmount: float
    account: dict = {}
    vatRate: float = 0.0


class InvoiceResponse(BaseModel):
    purchaseInvoiceNumber: int
    voucherId: int | None = None
    file: dict = {}  # {"fileName": ..., "fileRef": ...} for the scanned document
    supplier: dict = {}
    date: str
    currency: str = "DKK"
    grossAmount: float
    netAmount: float = 0.0
    vatAmount: float = 0.0
    lines: list[InvoiceLineResponse] = []


class EntryResponse(BaseModel):
    entryNumber: int
    voucherId: int
    entryType: str  # purchase_invoice | payment | journal_entry | credit_note
    account: dict = {}
    date: str
    description: str = ""
    debit: float = 0.0
    credit: float = 0.0
    currency: str = "DKK"


class HealthResponse(BaseModel):
    status: str = "ok"
    mode: str = "mock"
    dataGenerated: str = ""


class StatsResponse(BaseModel):
    vendors: int = 0
    accounts: int = 0
    invoices: int = 0
    lines: int = 0
