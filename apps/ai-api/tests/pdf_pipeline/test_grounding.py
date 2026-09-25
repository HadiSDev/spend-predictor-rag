from ai_api.grounding import ground_categorization
from ai_api.models import AccountChoice

CANDIDATES = [
    {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure", "level_2": "Technology", "level_3": "Cloud Infrastructure", "description": "cloud"},
    {"account_code": "6020", "account_name": "Software Subscriptions", "level_2": "Technology", "level_3": "SaaS & Licenses", "description": "saas"},
]
ACCOUNTS_BY_CODE = {c["account_code"]: c for c in CANDIDATES}


def _choice(code, level_1="Indirect"):
    return AccountChoice(account_code=code, account_name="whatever", level_1=level_1, confidence=0.9, rationale="r")


def test_valid_code_enriched_from_chart_keeps_model_l1():
    grounded, note = ground_categorization(_choice("6020", level_1="Direct"), CANDIDATES, ACCOUNTS_BY_CODE)
    assert grounded.account_code == "6020"
    assert grounded.account_name == "Software Subscriptions"
    assert grounded.level_2 == "Technology" and grounded.level_3 == "SaaS & Licenses"
    assert grounded.level_1 == "Direct"
    assert note == ""


def test_invalid_code_snaps_and_keeps_l1():
    grounded, note = ground_categorization(_choice("9999", level_1="Direct"), CANDIDATES, ACCOUNTS_BY_CODE)
    assert grounded.account_code == "6010"
    assert grounded.level_2 == "Technology" and grounded.level_3 == "Cloud Infrastructure"
    assert grounded.level_1 == "Direct"
    assert "9999" in note and "6010" in note


def test_invalid_code_no_candidates_blank_levels():
    grounded, note = ground_categorization(_choice("9999"), [], {})
    assert grounded.account_code == "9999"
    assert grounded.account_name == ""
    assert grounded.level_2 == "" and grounded.level_3 == ""
    assert "no candidates" in note
