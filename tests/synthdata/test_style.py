"""Tests for style.py: build_render_spec determinism, variety, and regime logic."""
from __future__ import annotations

import pytest
from faker import Faker

from spend_predictor.synthdata.render.renderer import list_templates
from spend_predictor.synthdata.style import build_render_spec


def _make_spec(seed: int, *, vat_regime: str = "EU"):
    Faker.seed(seed)
    fake = Faker()
    fake.seed_instance(seed)
    templates = list_templates()
    return build_render_spec(
        fake,
        vendor_name="Nimbus Cloud Services Inc.",
        buyer_name="Acme Buyer Ltd",
        invoice_date="2026-05-15",
        vat_regime=vat_regime,
        available_templates=templates,
    )


def test_determinism():
    """Same seed always yields identical spec."""
    s1 = _make_spec(42)
    s2 = _make_spec(42)
    assert s1.template_name == s2.template_name
    assert s1.style.accent == s2.style.accent
    assert s1.style.font_stack == s2.style.font_stack
    assert s1.style.show_logo == s2.style.show_logo
    assert s1.style.monogram == s2.style.monogram
    assert s1.po_number == s2.po_number
    assert s1.iban == s2.iban
    assert s1.due_date == s2.due_date


def test_eu_regime_has_iban_and_bank():
    """EU regime invoices include bank name and IBAN."""
    spec = _make_spec(1, vat_regime="EU")
    assert spec.bank_name is not None
    assert spec.iban is not None
    assert len(spec.iban) >= 10


def test_us_regime_no_iban():
    """US regime invoices do NOT include bank/IBAN."""
    spec = _make_spec(1, vat_regime="US")
    assert spec.bank_name is None
    assert spec.iban is None


def test_variety_across_seeds():
    """12 different seeds produce >=4 distinct template names and >=4 distinct accents."""
    templates_seen: set[str] = set()
    accents_seen: set[str] = set()
    for seed in range(12):
        spec = _make_spec(seed)
        templates_seen.add(spec.template_name)
        accents_seen.add(spec.style.accent)

    n_available = len(list_templates())
    # With 2 templates expect both; with more expect >=4 up to available
    expected_template_variety = min(n_available, 4)
    assert len(templates_seen) >= min(n_available, expected_template_variety), (
        f"Only {len(templates_seen)} distinct templates out of {n_available} available"
    )
    assert len(accents_seen) >= 4, f"Only {len(accents_seen)} distinct accents in 12 draws"


def test_monogram_from_initials():
    """Monogram is derived from vendor initials."""
    Faker.seed(0)
    fake = Faker()
    fake.seed_instance(0)
    templates = list_templates()
    spec = build_render_spec(
        fake,
        vendor_name="ByteForge Cloud GmbH",
        buyer_name="Buyer",
        invoice_date="2026-01-01",
        vat_regime="US",
        available_templates=templates,
    )
    assert spec.style.monogram == "BCG"


def test_due_date_derived_from_invoice_date_and_terms():
    """due_date is after invoice_date for any Net N terms."""
    from datetime import datetime
    spec = _make_spec(7, vat_regime="US")
    if spec.payment_terms.startswith("Net"):
        inv_dt = datetime.strptime("2026-05-15", "%Y-%m-%d")
        due_dt = datetime.strptime(spec.due_date, "%Y-%m-%d")
        assert due_dt >= inv_dt, "due_date should be >= invoice_date"


def test_extra_fields_present():
    """vendor_address and buyer_address are always non-empty strings."""
    spec = _make_spec(3)
    assert isinstance(spec.vendor_address, str) and len(spec.vendor_address) > 5
    assert isinstance(spec.buyer_address, str) and len(spec.buyer_address) > 5
    assert isinstance(spec.payment_terms, str) and len(spec.payment_terms) > 0
