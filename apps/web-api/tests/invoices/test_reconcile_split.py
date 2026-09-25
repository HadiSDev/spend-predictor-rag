"""Reconciling invoice lines against the document and against the ledger."""
from __future__ import annotations

from decimal import Decimal

from web_api import config as web_config
from web_api.reconcile import reconcile


def test_lines_matching_the_documents_own_total_reconcile():
    result = reconcile(
        Decimal("104.85"),
        total=Decimal("83.88"),
        tax=Decimal("0.00"),
        document_total=Decimal("104.85"),
    )

    assert result.ok


def test_a_missed_line_is_rejected_against_the_documents_own_total():
    result = reconcile(
        Decimal("523.00"),
        total=Decimal("538.07"),
        tax=Decimal("107.61"),
        document_total=Decimal("538.07"),
    )

    assert not result.ok
    assert "523.00" in result.reason and "538.07" in result.reason
    assert "document" in result.reason.lower()


def test_the_documents_own_subtotal_is_also_accepted():
    result = reconcile(
        Decimal("83.88"),
        total=Decimal("83.88"),
        tax=Decimal("0.00"),
        document_total=Decimal("104.85"),
        document_subtotal=Decimal("83.88"),
    )

    assert result.ok


def test_a_ledger_disagreement_is_flagged_not_rejected():
    result = reconcile(
        Decimal("104.85"),
        total=Decimal("83.88"),
        tax=Decimal("0.00"),
        document_total=Decimal("104.85"),
    )

    assert result.ok, "the extraction is accepted"
    assert result.totals_agree is False, "and the disagreement is reported"


def test_totals_that_agree_say_so():
    result = reconcile(
        Decimal("538.07"),
        total=Decimal("538.07"),
        tax=Decimal("107.61"),
        document_total=Decimal("538.07"),
    )

    assert result.ok and result.totals_agree is True


def test_no_document_total_means_nothing_to_compare():
    result = reconcile(Decimal("1000.00"), Decimal("1000.00"), Decimal("200.00"))

    assert result.totals_agree is None


def test_lines_matching_the_gross_total_still_reconcile():
    assert reconcile(Decimal("1000.00"), Decimal("1000.00"), Decimal("200.00")).ok


def test_lines_matching_the_net_total_still_reconcile():
    assert reconcile(Decimal("800.00"), Decimal("1000.00"), Decimal("200.00")).ok


def test_a_missed_line_is_still_rejected_against_the_ledger():
    result = reconcile(Decimal("300.00"), Decimal("1000.00"), Decimal("200.00"))

    assert not result.ok
    assert "1000.00" in result.reason and "800.00" in result.reason


def test_nothing_to_reconcile_against_at_all():
    result = reconcile(Decimal("7.00"), None, None)

    assert result.ok and result.checked is False


def test_rounding_does_not_reject_the_internal_check():
    assert reconcile(
        Decimal("4812.01"), total=Decimal("4812.00"), tax=None,
        document_total=Decimal("4812.00"),
    ).ok


def test_the_internal_check_is_tighter_than_the_cross_source_one(monkeypatch):
    monkeypatch.setattr(web_config, "DOC_RECONCILE_TOLERANCE_PCT", 0.01)
    monkeypatch.setattr(web_config, "DOC_INTERNAL_TOLERANCE_PCT", 0.001)
    monkeypatch.setattr(web_config, "DOC_INTERNAL_TOLERANCE_ABS", 0.05)

    assert reconcile(Decimal("1008.00"), Decimal("1000.00"), None).ok
    assert not reconcile(
        Decimal("1008.00"), total=Decimal("1000.00"), tax=None,
        document_total=Decimal("1000.00"),
    ).ok


def test_gross_against_net_is_not_a_disagreement():
    result = reconcile(
        Decimal("104.85"),
        total=Decimal("83.88"),
        tax=Decimal("0.00"),
        document_total=Decimal("104.85"),
        document_subtotal=Decimal("83.88"),
    )

    assert result.ok
    assert result.totals_agree is True


def test_the_aquatuning_invoice_is_accepted():
    lines = Decimal("36.64") + Decimal("31.41") + Decimal("20.90") + Decimal("15.90")
    assert lines == Decimal("104.85")

    result = reconcile(
        lines,
        total=Decimal("83.88"),
        tax=Decimal("0.00"),
        document_total=Decimal("104.85"),
        document_subtotal=Decimal("83.88"),
    )

    assert result.ok
    assert result.totals_agree is True


def test_the_aquatuning_invoice_fails_the_rule_it_replaces():
    lines = Decimal("36.64") + Decimal("31.41") + Decimal("20.90") + Decimal("15.90")

    result = reconcile(lines, Decimal("83.88"), Decimal("0.00"))

    assert not result.ok
