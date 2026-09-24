"""Capture scrubbed Billy fixtures for the connector tests.

Pulls a small representative slice of a real Billy organization and rewrites
every identifying value — organization, supplier names, CVR/VAT numbers, ids —
while preserving the exact field set and envelope shape the API returns. Tests
built on these fail when Billy's *shape* changes, which is the point; they carry
no real bookkeeping.

Selection favours coverage over volume: every originator kind seen in the live
survey, a voided pair, a bill with an attachment, and accounts on both sides of
the archived/taxed flags.

GETs only. Deleted with the spike scripts by task 8.3.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.billysbilling.com/v2"
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "billy"

client = httpx.Client(base_url=BASE_URL, timeout=60)
H = {"X-Access-Token": os.environ["BILLY_ACCESS_TOKEN"]}

# Names substituted in, so a fixture never carries a real trading relationship.
SUPPLIERS = [
    "Nordwind Cloud ApS", "Kellerman Print A/S", "Vitre Office Supplies",
    "Sørensen Logistik ApS", "Halden Software AB", "Meridian Facilities ApS",
]
_id_map: dict[str, str] = {}


def fake_id(real: str | None) -> str | None:
    """Stable pseudonym for a Billy id, so cross-references still line up."""
    if not real:
        return real
    if real not in _id_map:
        digest = hashlib.sha256(real.encode()).hexdigest()
        _id_map[real] = digest[:22]
    return _id_map[real]


#: Set while scrubbing a chart of accounts. Account and nature names are a
#: standard Danish chart — not a trading relationship — and pseudonymising them
#: would leave fixtures that no longer look like a chart of accounts.
_keep_names = False


def scrub(node, key: str | None = None):
    if isinstance(node, dict):
        return {k: scrub(v, k) for k, v in node.items()}
    if isinstance(node, list):
        return [scrub(v) for v in node]
    if isinstance(node, str):
        if key == "name" and _keep_names:
            return node
        if key and (key == "id" or key.endswith("Id")) and len(node) > 15:
            return fake_id(node)
        if key == "ownerReference" and ":" in node:
            kind, _, rid = node.partition(":")
            return f"{kind}:{fake_id(rid)}"
        if key == "originatorReference" and ":" in node:
            kind, _, rid = node.partition(":")
            return f"{kind}:{fake_id(rid)}"
        if key in ("name", "contactName", "supplier", "originatorName", "organizationName"):
            return SUPPLIERS[int(hashlib.sha256(node.encode()).hexdigest(), 16) % len(SUPPLIERS)]
        if key in ("registrationNo", "vatNo"):
            return "DK" + str(int(hashlib.sha256(node.encode()).hexdigest(), 16) % 10**8).zfill(8)
        if key in ("downloadUrl", "originalUrl"):
            return "https://billysbilling-eu.s3.eu-north-1.amazonaws.com/scrubbed.pdf"
        if key in ("email", "phone", "street", "cityText", "zipcodeText", "dataJson"):
            return ""
    return node


def get(path, **params):
    r = client.get(path, headers=H, params=params or None)
    r.raise_for_status()
    return r.json()


def write(name: str, body, keep_names: bool = False) -> None:
    global _keep_names
    OUT.mkdir(parents=True, exist_ok=True)
    _keep_names = keep_names
    (OUT / f"{name}.json").write_text(json.dumps(scrub(body), indent=2, ensure_ascii=False) + "\n")
    _keep_names = False
    print(f"  wrote {name}.json")


# -- Organization ------------------------------------------------------------
write("organization", get("/organization"))

# -- Accounts: keep a slice covering archived / taxed / untaxed --------------
accounts: list[dict] = []
page = 1
while True:
    body = get("/accounts", page=page, pageSize=100)
    accounts.extend(body["accounts"])
    if page >= (body["meta"]["paging"]["pageCount"] or 1):
        break
    page += 1

# The whole chart, not a slice: postings and bill lines name their account by
# id, so a partial chart would leave the connector unable to resolve most of
# them — and "account not in the chart" is exactly the error path we do not want
# tests walking by accident.
flags = {(bool(a.get("isArchived")), bool(a.get("taxRateId"))) for a in accounts}
print(f"  chart: {len(accounts)} accounts, (archived, taxed) combinations: {sorted(flags)}")
write("accounts", {"accounts": accounts,
                   "meta": {"paging": {"page": 1, "pageSize": 100,
                                       "pageCount": 1, "total": len(accounts)}}},
      keep_names=True)
write("account_natures", get("/accountNatures", pageSize=100), keep_names=True)

# -- Contacts: suppliers plus one customer-only, to prove the filter ---------
# Every supplier, not a slice: bills name their contact by id and leave
# `contactName` null, so a partial contact book leaves invoices unnamed.
suppliers = get("/contacts", pageSize=200, isSupplier="true")["contacts"]
everyone = get("/contacts", pageSize=50)["contacts"]
customer_only = [c for c in everyone if c.get("isCustomer") and not c.get("isSupplier")][:1]
write("contacts_suppliers",
      {"contacts": suppliers,
       "meta": {"paging": {"page": 1, "pageSize": 100, "pageCount": 1,
                           "total": len(suppliers)}}})
write("contacts_all",
      {"contacts": suppliers + customer_only,
       "meta": {"paging": {"page": 1, "pageSize": 100, "pageCount": 1,
                           "total": len(suppliers) + len(customer_only)}}})

# -- Transactions: one per originator kind, plus a voided pair ---------------
txs: list[dict] = []
page = 1
while True:
    body = get("/transactions", page=page, pageSize=100,
               include="transaction.postings:embed")
    txs.extend(body["transactions"])
    if page >= (body["meta"]["paging"]["pageCount"] or 1):
        break
    page += 1

by_kind: dict[str, dict] = {}
for t in txs:
    kind = str(t.get("originatorReference") or "").split(":")[0]
    if kind and kind not in by_kind and t.get("postings"):
        by_kind[kind] = t
voided = [t for t in txs if t.get("isVoided")][:1] + [t for t in txs if t.get("isVoid")][:1]
selection = list(by_kind.values()) + [t for t in voided if t not in by_kind.values()]
print(f"  transaction kinds captured: {sorted(by_kind)}")
write("transactions", {"transactions": selection,
                       "meta": {"paging": {"page": 1, "pageSize": 100,
                                           "pageCount": 1, "total": len(selection)}}})

# -- One bill, with its lines, exactly as the connector will fetch it --------
bill_tx = by_kind.get("bill")
bill_id = str(bill_tx["originatorReference"]).split(":", 1)[1]
write("bill_single", get(f"/bills/{bill_id}", include="bill.lines"))

atts = get("/attachments", pageSize=50)["attachments"]
owned = [a for a in atts if str(a.get("ownerReference", "")).startswith(f"bill:{bill_id}")]
if not owned:
    # Any bill-owned attachment still exercises the resolution path.
    owned = [a for a in atts if str(a.get("ownerReference", "")).startswith("bill:")][:1]
write("attachments", {"attachments": owned,
                      "meta": {"paging": {"page": 1, "pageSize": 100,
                                          "pageCount": 1, "total": len(owned)}}})
if owned:
    write("file", get(f"/files/{owned[0]['fileId']}"))

print(f"\nFixtures written to {OUT}")
