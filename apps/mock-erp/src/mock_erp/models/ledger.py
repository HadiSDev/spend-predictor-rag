"""Chart-of-accounts and GL entry response models."""

from pydantic import BaseModel


class AccountResponse(BaseModel):
    accountNumber: int
    name: str
    accountType: str
    parentAccountNumber: int | None = None
    isActive: bool = True
    withVat: bool = False
    balance: float = 0.0


class EntryResponse(BaseModel):
    entryNumber: int
    voucherId: int
    entryType: str
    account: dict = {}
    date: str
    description: str = ""
    debit: float = 0.0
    credit: float = 0.0
    currency: str = "DKK"
