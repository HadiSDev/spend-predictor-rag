from spend_predictor.grounding import ground_categorization
from spend_predictor.models import AccountChoice

CANDIDATES = [
    {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure", "level2": "Technology", "level3": "Cloud Infrastructure", "description": "cloud"},
    {"account_code": "6020", "account_name": "Software Subscriptions", "level2": "Technology", "level3": "SaaS & Licenses", "description": "saas"},
]
ACCOUNTS_BY_CODE = {c["account_code"]: c for c in CANDIDATES}


def _choice(code, level1="Indirect"):
    return AccountChoice(account_code=code, account_name="whatever", level1=level1, confidence=0.9, rationale="r")


def test_valid_code_enriched_from_chart_keeps_model_l1():
    grounded, note = ground_categorization(_choice("6020", level1="Direct"), CANDIDATES, ACCOUNTS_BY_CODE)
    assert grounded.account_code == "6020"
    assert grounded.account_name == "Software Subscriptions"
    assert grounded.level2 == "Technology" and grounded.level3 == "SaaS & Licenses"
    assert grounded.level1 == "Direct"  # from the model, not the chart
    assert note == ""


def test_invalid_code_snaps_and_keeps_l1():
    grounded, note = ground_categorization(_choice("9999", level1="Direct"), CANDIDATES, ACCOUNTS_BY_CODE)
    assert grounded.account_code == "6010"
    assert grounded.level2 == "Technology" and grounded.level3 == "Cloud Infrastructure"
    assert grounded.level1 == "Direct"
    assert "9999" in note and "6010" in note


def test_invalid_code_no_candidates_blank_levels():
    grounded, note = ground_categorization(_choice("9999"), [], {})
    assert grounded.account_code == "9999"
    assert grounded.level2 == "" and grounded.level3 == ""
    assert "no candidates" in note
