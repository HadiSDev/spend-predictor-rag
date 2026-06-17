# tests/synthdata/test_sampler.py
from spend_predictor.synthdata.sampler import InvoicePlan, sample_plans

_ACCOUNTS = [
    {"account_code": "6010", "account_name": "Cloud Hosting & Infrastructure",
     "level2": "Technology", "level3": "Cloud Infrastructure", "description": "cloud servers"},
    {"account_code": "6800", "account_name": "Travel - Airfare",
     "level2": "Travel & Entertainment", "level3": "Airfare", "description": "flights"},
]


def test_sampling_is_deterministic_for_a_seed():
    a = sample_plans(5, seed=7, accounts=_ACCOUNTS)
    b = sample_plans(5, seed=7, accounts=_ACCOUNTS)
    assert [p.invoice_number for p in a] == [p.invoice_number for p in b]
    assert [p.total for p in a] == [p.total for p in b]


def test_each_plan_reconciles_and_has_single_account():
    for p in sample_plans(20, seed=1, accounts=_ACCOUNTS):
        assert isinstance(p, InvoicePlan)
        line_sum = round(sum(l.amount for l in p.lines), 2)
        assert line_sum == round(p.subtotal, 2)
        assert round(p.subtotal + p.tax, 2) == round(p.total, 2)
        assert p.account in _ACCOUNTS  # exactly one chart account drives the invoice
        assert p.level1 in {"Direct", "Indirect"}
        assert all(l.description for l in p.lines)


def test_vat_regime_controls_vat_and_country_fields():
    plans = sample_plans(40, seed=3, accounts=_ACCOUNTS)
    eu = [p for p in plans if p.vat_regime == "EU"]
    us = [p for p in plans if p.vat_regime == "US"]
    assert eu and us  # both regimes appear
    for p in eu:
        assert p.tax > 0 and p.supplier_vat_number and p.buyer_country_code
        assert all(l.vat_rate and l.vat_code for l in p.lines)
    for p in us:
        assert p.tax == 0 and not p.supplier_vat_number
        assert all(l.vat_rate in (None, 0) for l in p.lines)
