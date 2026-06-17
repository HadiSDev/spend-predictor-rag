import json

from spend_predictor.models import CategorizedInvoice, ExtractedInvoice, LineItem
from spend_predictor.synthdata.score import anls_field, score_fixture, score_fixtures


def test_anls_field_rewards_near_matches():
    assert anls_field("Nimbus Cloud Services Inc.", "Nimbus Cloud Services Inc.") == 1.0
    assert anls_field("", "Anything") == 0.0
    assert anls_field("Nimbus Cloud Servces Inc", "Nimbus Cloud Services Inc.") > 0.8


def _labels() -> dict:
    inv = ExtractedInvoice(
        vendor_name="Nimbus Cloud Services Inc.", invoice_number="INV-1",
        currency="USD", line_items=[LineItem(description="hosting", amount=100.0)],
        subtotal=100.0, tax=0.0, total=100.0,
    )
    return {"invoice": inv.model_dump(),
            "category": {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
                         "level1": "Direct", "level2": "Technology", "level3": "Cloud Infrastructure"}}


def test_score_fixture_perfect_prediction():
    labels = _labels()
    extracted = ExtractedInvoice(**labels["invoice"])
    categorized = CategorizedInvoice(
        account_code="6010", account_name="Cloud Hosting & Infrastructure",
        level1="Direct", level2="Technology", level3="Cloud Infrastructure",
        confidence=0.9, rationale="r")
    res = score_fixture(labels, extracted, categorized)
    assert res["fields"]["vendor_name"] == 1.0
    assert res["category"]["account_code"] is True
    assert res["category"]["level1"] is True


def test_score_fixture_handles_pipeline_failure():
    res = score_fixture(_labels(), None, None)  # pipeline produced nothing
    assert res["fields"]["vendor_name"] == 0.0
    assert res["category"]["account_code"] is False


def test_score_fixtures_aggregates(tmp_path):
    labels = _labels()
    fdir = tmp_path / "00000"
    fdir.mkdir()
    (fdir / "labels.json").write_text(json.dumps(labels))
    (fdir / "invoice.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "manifest.jsonl").write_text(json.dumps({"id": "00000"}) + "\n")

    def fake_pipeline(pdf_path, buyer_context):
        extracted = ExtractedInvoice(**labels["invoice"])
        categorized = CategorizedInvoice(
            account_code="6010", account_name="Cloud Hosting & Infrastructure",
            level1="Direct", level2="Technology", level3="Cloud Infrastructure",
            confidence=0.9, rationale="r")
        return extracted, categorized

    report = score_fixtures(tmp_path, run_pipeline=fake_pipeline)
    assert report["count"] == 1
    assert report["category_accuracy"]["account_code"] == 1.0
    assert report["field_anls"]["vendor_name"] == 1.0
