"""Capture scrubbed Billy fixtures for the connector tests."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.billysbilling.com/v2"
OUT = Path(__file__).resolve().parent.parent / "tests" / "connectors" / "fixtures" / "billy"

client = httpx.Client(base_url=BASE_URL, timeout=60)
H = {"X-Access-Token": os.environ["BILLY_ACCESS_TOKEN"]}

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


def scrub(node, key: str | None = None, keep_names: bool = False):
    if isinstance(node, dict):
        return {k: scrub(v, k, keep_names) for k, v in node.items()}
    if isinstance(node, list):
        return [scrub(v, keep_names=keep_names) for v in node]
    if isinstance(node, str):
        if key == "name" and keep_names:
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
    OUT.mkdir(parents=True, exist_ok=True)
    scrubbed = scrub(body, keep_names=keep_names)
    (OUT / f"{name}.json").write_text(json.dumps(scrubbed, indent=2, ensure_ascii=False) + "\n")
    print(f"  wrote {name}.json")


write("organization", get("/organization"))

accounts: list[dict] = []
page = 1
while True:
    body = get("/accounts", page=page, pageSize=100)
    accounts.extend(body["accounts"])
    if page >= (body["meta"]["paging"]["pageCount"] or 1):
        break
    page += 1

flags = {(bool(a.get("isArchived")), bool(a.get("taxRateId"))) for a in accounts}
print(f"  chart: {len(accounts)} accounts, (archived, taxed) combinations: {sorted(flags)}")
write("accounts", {"accounts": accounts,
                   "meta": {"paging": {"page": 1, "pageSize": 100,
                                       "pageCount": 1, "total": len(accounts)}}},
      keep_names=True)
write("account_natures", get("/accountNatures", pageSize=100), keep_names=True)

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

bill_tx = by_kind.get("bill")
bill_id = str(bill_tx["originatorReference"]).split(":", 1)[1]
write("bill_single", get(f"/bills/{bill_id}", include="bill.lines"))

atts = get("/attachments", pageSize=50)["attachments"]
owned = [a for a in atts if str(a.get("ownerReference", "")).startswith(f"bill:{bill_id}")]
if not owned:
    owned = [a for a in atts if str(a.get("ownerReference", "")).startswith("bill:")][:1]
write("attachments", {"attachments": owned,
                      "meta": {"paging": {"page": 1, "pageSize": 100,
                                          "pageCount": 1, "total": len(owned)}}})
if owned:
    write("file", get(f"/files/{owned[0]['fileId']}"))

print(f"\nFixtures written to {OUT}")
