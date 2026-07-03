"""Tests for the deterministic keyword categorizer used by the sync runner."""
from __future__ import annotations

from ai_api.sync.categorizer import categorize, default_candidates


def test_known_descriptions_map_to_expected_accounts():
    candidates = default_candidates()
    cases = {
        "Cloud server - monthly hosting": "6010",
        "API usage - monthly subscription": "6015",
        "SaaS license - monthly seat": "6020",
        "Legal retainer - monthly": "6610",
        "Office rent - monthly": "6910",
        "Package delivery - domestic": "7000",
        "Social media campaign - monthly": "6700",
        "Hotel - 3 nights business": "6810",
        "Conference call service": "6030",
    }
    for desc, expected_code in cases.items():
        match = categorize(desc, native_account_code=None, candidates=candidates)
        assert match.matched, f"{desc!r} should match"
        assert match.account_code == expected_code, f"{desc!r} -> {match.account_code}, want {expected_code}"
        assert 0.0 < match.confidence <= 1.0


def test_month_suffix_is_ignored():
    candidates = default_candidates()
    a = categorize("Cloud server - monthly hosting", None, candidates)
    b = categorize("Cloud server - monthly hosting (M7)", None, candidates)
    assert a.account_code == b.account_code == "6010"


def test_unmatchable_description_fails():
    candidates = default_candidates()
    match = categorize("zzz qqq xyzzy", native_account_code=None, candidates=candidates)
    assert not match.matched
    assert match.account_code is None
    assert match.confidence == 0.0


def test_deterministic_same_input_same_output():
    candidates = default_candidates()
    first = categorize("Team lunch - monthly", None, candidates)
    second = categorize("Team lunch - monthly", None, candidates)
    assert first == second


def test_ground_truth_derives_from_native_code():
    candidates = default_candidates()
    match = categorize("ambiguous service fee", native_account_code="6020", candidates=candidates)
    assert match.gt_account_code == "6020"
    assert match.gt_level_2 == "Technology"


def test_level_1_direct_for_cogs():
    candidates = default_candidates()
    match = categorize("raw materials purchase", native_account_code="4000", candidates=candidates)
    assert match.gt_level_1 == "Direct"
