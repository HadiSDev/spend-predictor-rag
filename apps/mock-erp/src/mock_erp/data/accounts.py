"""Standard e-conomic-style chart of accounts for the mock ERP."""


def _with_vat(account_type: str) -> bool:
    return account_type in ("expense",)


_RAW: list[dict] = [
    {"accountNumber": 1000, "name": "Cash", "accountType": "asset", "parentAccountNumber": None},
    {"accountNumber": 1100, "name": "Accounts Receivable", "accountType": "asset", "parentAccountNumber": None},
    {"accountNumber": 1200, "name": "Inventory", "accountType": "asset", "parentAccountNumber": None},
    {"accountNumber": 2100, "name": "Accounts Payable", "accountType": "liability", "parentAccountNumber": None},
    {"accountNumber": 2200, "name": "VAT Payable", "accountType": "liability", "parentAccountNumber": None},
    {"accountNumber": 3000, "name": "Revenue", "accountType": "income", "parentAccountNumber": None},
    {"accountNumber": 4000, "name": "Cost of Goods Sold", "accountType": "expense", "parentAccountNumber": None},
    {"accountNumber": 6010, "name": "Cloud Hosting & Infrastructure", "accountType": "expense", "parentAccountNumber": 6000},
    {"accountNumber": 6015, "name": "Third-Party APIs & Data", "accountType": "expense", "parentAccountNumber": 6000},
    {"accountNumber": 6020, "name": "Software Subscriptions", "accountType": "expense", "parentAccountNumber": 6000},
    {"accountNumber": 6030, "name": "Telecommunications", "accountType": "expense", "parentAccountNumber": 6000},
    {"accountNumber": 6500, "name": "Office Supplies", "accountType": "expense", "parentAccountNumber": 6500},
    {"accountNumber": 6510, "name": "Office Equipment", "accountType": "expense", "parentAccountNumber": 6500},
    {"accountNumber": 6600, "name": "Professional Services", "accountType": "expense", "parentAccountNumber": None},
    {"accountNumber": 6610, "name": "Legal Fees", "accountType": "expense", "parentAccountNumber": None},
    {"accountNumber": 6620, "name": "Accounting & Audit", "accountType": "expense", "parentAccountNumber": None},
    {"accountNumber": 6700, "name": "Marketing & Advertising", "accountType": "expense", "parentAccountNumber": None},
    {"accountNumber": 6800, "name": "Travel - Airfare", "accountType": "expense", "parentAccountNumber": 6800},
    {"accountNumber": 6810, "name": "Travel - Lodging", "accountType": "expense", "parentAccountNumber": 6800},
    {"accountNumber": 6820, "name": "Meals & Entertainment", "accountType": "expense", "parentAccountNumber": 6800},
    {"accountNumber": 6900, "name": "Utilities", "accountType": "expense", "parentAccountNumber": None},
    {"accountNumber": 6910, "name": "Rent & Lease", "accountType": "expense", "parentAccountNumber": None},
    {"accountNumber": 7000, "name": "Shipping & Freight", "accountType": "expense", "parentAccountNumber": None},
    {"accountNumber": 7050, "name": "Contractors", "accountType": "expense", "parentAccountNumber": None},
    {"accountNumber": 7100, "name": "Training & Development", "accountType": "expense", "parentAccountNumber": None},
]

ACCOUNTS: list[dict] = [
    {**a, "withVat": _with_vat(a["accountType"])} for a in _RAW
]


def account_name(account_number: int) -> str:
    """The chart name of ``account_number``, or ``"Unknown"``."""
    for account in ACCOUNTS:
        if account["accountNumber"] == account_number:
            return account["name"]
    return "Unknown"
