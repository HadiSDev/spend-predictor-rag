from spend_predictor.grounding import ground_categorization
from spend_predictor.models import CategorizedInvoice

CANDIDATES = [
    {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure", "category": "IT", "description": "cloud"},
    {"account_code": "6020", "account_name": "Software Subscriptions", "category": "IT", "description": "saas"},
]
ACCOUNTS_BY_CODE = {c["account_code"]: c for c in CANDIDATES}


def _cat(code, name="X", category="Y"):
    return CategorizedInvoice(
        account_code=code, account_name=name, category=category, confidence=0.9, rationale="r"
    )


def test_valid_code_is_kept_and_canonicalized():
    grounded, note = ground_categorization(_cat("6020", name="wrong", category="wrong"), CANDIDATES, ACCOUNTS_BY_CODE)
    assert grounded.account_code == "6020"
    # name/category corrected to the chart's canonical values
    assert grounded.account_name == "Software Subscriptions"
    assert grounded.category == "IT"
    assert note == ""


def test_invalid_code_snaps_to_top_candidate_with_note():
    grounded, note = ground_categorization(_cat("8010"), CANDIDATES, ACCOUNTS_BY_CODE)
    assert grounded.account_code == "6010"
    assert grounded.account_name == "Cloud Hosting & Infrastructure"
    assert grounded.category == "IT"
    assert "8010" in note and "6010" in note


def test_invalid_code_no_candidates_is_flagged():
    grounded, note = ground_categorization(_cat("8010"), [], {})
    assert grounded.account_code == "8010"  # nothing to snap to
    assert "8010" in note and "no candidates" in note
