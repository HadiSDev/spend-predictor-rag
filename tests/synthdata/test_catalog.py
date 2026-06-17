# tests/synthdata/test_catalog.py
"""Tests for the deterministic item catalog."""
from faker import Faker

from spend_predictor.synthdata.catalog import (
    ITEM_CATALOG,
    line_descriptions,
    vendor_name,
)

_ALL_CODES = [
    "6010", "6015", "6020", "6030",
    "6500", "6510",
    "6600", "6610", "6620",
    "6700",
    "6800", "6810", "6820",
    "6900", "6910",
    "7000", "7050", "7100",
]

_SAMPLE_ACCOUNT = {
    "account_code": "6010",
    "account_name": "Cloud Hosting & Infrastructure",
    "level2": "Technology",
    "level3": "Cloud Infrastructure",
    "description": "cloud servers",
}


# ---------------------------------------------------------------------------
# ITEM_CATALOG coverage
# ---------------------------------------------------------------------------

def test_catalog_covers_all_18_accounts():
    assert set(_ALL_CODES) <= set(ITEM_CATALOG.keys()), (
        f"Missing codes: {set(_ALL_CODES) - set(ITEM_CATALOG.keys())}"
    )


def test_catalog_has_at_least_8_templates_per_account():
    for code in _ALL_CODES:
        assert len(ITEM_CATALOG[code]) >= 8, f"Code {code} has fewer than 8 templates"


# ---------------------------------------------------------------------------
# line_descriptions
# ---------------------------------------------------------------------------

def _seeded_faker(seed: int = 42) -> Faker:
    Faker.seed(seed)
    f = Faker()
    f.seed_instance(seed)
    return f


def test_line_descriptions_returns_requested_count():
    fake = _seeded_faker(1)
    for n in [1, 2, 3, 4]:
        result = line_descriptions("6010", n, fake)
        assert len(result) == n, f"Expected {n} items, got {len(result)}"


def test_line_descriptions_all_non_empty():
    fake = _seeded_faker(2)
    result = line_descriptions("6700", 4, fake)
    assert all(desc and desc.strip() for desc in result)


def test_line_descriptions_variety_within_draw():
    """20 draws from one account should yield >=10 distinct descriptions."""
    fake = _seeded_faker(3)
    result = line_descriptions("6020", 20, fake)
    assert len(set(result)) >= 10, (
        f"Only {len(set(result))} distinct descriptions in 20 draws"
    )


def test_line_descriptions_all_accounts_work():
    """All 18 account codes must produce non-empty results without error."""
    fake = _seeded_faker(4)
    for code in _ALL_CODES:
        result = line_descriptions(code, 3, fake)
        assert len(result) == 3
        assert all(desc for desc in result), f"Empty description for {code}"


def test_line_descriptions_unknown_code_falls_back_gracefully():
    fake = _seeded_faker(5)
    result = line_descriptions("9999", 2, fake)
    assert len(result) == 2
    assert all(desc for desc in result)
    # should not produce bare "item N"
    for desc in result:
        assert desc.lower() != "item 1" and desc.lower() != "item 2"


def test_line_descriptions_is_seed_deterministic():
    a = line_descriptions("6800", 3, _seeded_faker(77))
    b = line_descriptions("6800", 3, _seeded_faker(77))
    assert a == b


# ---------------------------------------------------------------------------
# vendor_name
# ---------------------------------------------------------------------------

def test_vendor_name_is_non_empty():
    fake = _seeded_faker(10)
    name = vendor_name(_SAMPLE_ACCOUNT, fake)
    assert name and name.strip()


def test_vendor_name_variety():
    """10 draws should yield >=8 distinct vendor names (not all identical)."""
    names = [vendor_name(_SAMPLE_ACCOUNT, _seeded_faker(i)) for i in range(10)]
    assert len(set(names)) >= 8, f"Only {len(set(names))} distinct names: {names}"


def test_vendor_name_is_seed_deterministic():
    a = vendor_name(_SAMPLE_ACCOUNT, _seeded_faker(99))
    b = vendor_name(_SAMPLE_ACCOUNT, _seeded_faker(99))
    assert a == b


def test_vendor_name_all_accounts():
    """vendor_name must not raise for any of the 18 account codes."""
    for code in _ALL_CODES:
        acct = {**_SAMPLE_ACCOUNT, "account_code": code}
        name = vendor_name(acct, _seeded_faker(0))
        assert name and name.strip(), f"Empty vendor name for {code}"


def test_vendor_name_legal_style():
    acct = {**_SAMPLE_ACCOUNT, "account_code": "6610"}
    # Legal cluster always uses "X & Y Suffix" style
    names = [vendor_name(acct, _seeded_faker(i)) for i in range(5)]
    assert all("&" in n for n in names), f"Expected '&' in all legal names: {names}"
