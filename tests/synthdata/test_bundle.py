import json

from spend_predictor.models import ExtractedInvoice, LineItem
from spend_predictor.synthdata.bundle import (
    append_manifest, category_from_account, load_fixture, write_labels,
)
from spend_predictor.synthdata.erp import build_journal
from spend_predictor.synthdata.profiles import PROFILES


def test_category_from_account():
    acct = {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
            "level2": "Technology", "level3": "Cloud Infrastructure", "description": "x"}
    cat = category_from_account(acct, "Direct")
    assert cat == {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
                   "level1": "Direct", "level2": "Technology", "level3": "Cloud Infrastructure"}


def test_write_and_load_fixture_roundtrip(tmp_path):
    inv = ExtractedInvoice(vendor_name="ACME",
                           line_items=[LineItem(description="x", amount=100.0)],
                           subtotal=100.0, tax=0.0, total=100.0)
    cat = {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
           "level1": "Direct", "level2": "Technology", "level3": "Cloud Infrastructure"}
    journal = build_journal(inv, "6010", "Cloud Hosting & Infrastructure")
    fdir = tmp_path / "0001"
    write_labels(fdir, invoice=inv, category=cat, buyer=PROFILES[0], journal=journal)

    loaded = load_fixture(fdir)
    assert loaded["category"] == cat
    assert loaded["invoice"]["total"] == 100.0
    assert loaded["buyer"]["name"] == PROFILES[0].name
    assert loaded["buyer"]["business_description"] == PROFILES[0].business_description
    assert len(loaded["journal"]) == len(journal)


def test_append_manifest_writes_one_object_per_line(tmp_path):
    mp = tmp_path / "manifest.jsonl"
    append_manifest(mp, {"id": "0001", "account_code": "6010"})
    append_manifest(mp, {"id": "0002", "account_code": "6800"})
    lines = mp.read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[1])["id"] == "0002"
