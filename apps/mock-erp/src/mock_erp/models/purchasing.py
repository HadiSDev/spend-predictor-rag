"""Supplier and purchase-invoice response models."""

from pydantic import BaseModel


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
    file: dict = {}
    supplier: dict = {}
    date: str
    currency: str = "DKK"
    grossAmount: float
    netAmount: float = 0.0
    vatAmount: float = 0.0
    lines: list[InvoiceLineResponse] = []
