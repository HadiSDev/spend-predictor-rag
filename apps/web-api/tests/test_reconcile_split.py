"""Two checks, because there are two questions.

The old rule asked whether *the document's lines* added up to *the ERP's total*.
Two systems, two VAT conventions, one comparison — and it conflated a question
that has an exact answer with one that does not:

* **"Did we read this document correctly?"** is arithmetic within one source. If
  the lines do not sum to the total printed on the same page, we misread the
  page. That is what rejection is for.
* **"Do the supplier and the bookkeeper agree?"** has no exact answer. A German
  supplier printing gross and a Danish bookkeeper posting net are both right; a
  partial posting, a credit note applied on one side and a typo are all real.
  Rejecting there means the reviewer never sees the lines and cannot tell a
  misreading from a mis-posting.

The internal check is *stricter* than the old rule, not weaker: it compares
against a figure from the same document rather than one that may legitimately
differ.
"""
from __future__ import annotations

from decimal import Decimal

from web_api import config as web_config
from web_api.reconcile import reconcile


# -- Check 1: the document against itself ------------------------------------


def test_lines_matching_the_documents_own_total_reconcile():
    """Aquatuning, in full. Every figure real, and the document exact.

    Lines printed gross (36,64 + 31,41 + 20,90 = 88,95), shipping stated only in
    the totals block (15,90), the document's own total 104,85 — and a Danish
    posting of the net 83,88 with `tax = 0.00`, so the old rule's `total - tax`
    branch was identical to its `total` branch and bought nothing.
    """
    result = reconcile(
        Decimal("104.85"),
        total=Decimal("83.88"),
        tax=Decimal("0.00"),
        document_total=Decimal("104.85"),
    )

    assert result.ok


def test_a_missed_line_is_rejected_against_the_documents_own_total():
    """CompuMail: 484,00 + 39,00 read, and a 15,07 payment fee row missed.

    The ledger agrees with the document to the øre, so this is unambiguously a
    reading failure — and the message must say so instead of blaming the ledger.
    """
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
    """A document printing both figures may have its lines stated either way."""
    result = reconcile(
        Decimal("83.88"),
        total=Decimal("83.88"),
        tax=Decimal("0.00"),
        document_total=Decimal("104.85"),
        document_subtotal=Decimal("83.88"),
    )

    assert result.ok


# -- Check 2: the document against the ledger --------------------------------


def test_a_ledger_disagreement_is_flagged_not_rejected():
    """The lines add up to the page they came from. The ledger says otherwise.

    That is information for a reviewer, not grounds for throwing the reading
    away — which is the position the Aquatuning invoice has been in.
    """
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
    """Null, not True. "Nothing to compare" and "compared and agreed" are
    different claims, and a client that cannot tell them apart will present an
    unread document as a verified one."""
    result = reconcile(Decimal("1000.00"), Decimal("1000.00"), Decimal("200.00"))

    assert result.totals_agree is None


# -- The fallback: no document total, so today's rule stands unchanged --------


def test_lines_matching_the_gross_total_still_reconcile():
    assert reconcile(Decimal("1000.00"), Decimal("1000.00"), Decimal("200.00")).ok


def test_lines_matching_the_net_total_still_reconcile():
    assert reconcile(Decimal("800.00"), Decimal("1000.00"), Decimal("200.00")).ok


def test_a_missed_line_is_still_rejected_against_the_ledger():
    result = reconcile(Decimal("300.00"), Decimal("1000.00"), Decimal("200.00"))

    assert not result.ok
    assert "1000.00" in result.reason and "800.00" in result.reason


def test_nothing_to_reconcile_against_at_all():
    """No ledger total and no document total: judged only on producing lines."""
    result = reconcile(Decimal("7.00"), None, None)

    assert result.ok and result.checked is False


# -- The internal tolerance --------------------------------------------------


def test_rounding_does_not_reject_the_internal_check():
    assert reconcile(
        Decimal("4812.01"), total=Decimal("4812.00"), tax=None,
        document_total=Decimal("4812.00"),
    ).ok


def test_the_internal_check_is_tighter_than_the_cross_source_one(monkeypatch):
    """Same-document arithmetic is near-exact, so its tolerance is not the one
    sized for two systems disagreeing. A gap the ledger comparison would forgive
    must still be a misreading of the page it was printed on."""
    monkeypatch.setattr(web_config, "DOC_RECONCILE_TOLERANCE_PCT", 0.01)
    monkeypatch.setattr(web_config, "DOC_INTERNAL_TOLERANCE_PCT", 0.001)
    monkeypatch.setattr(web_config, "DOC_INTERNAL_TOLERANCE_ABS", 0.05)

    # 8.00 out of 1000 — inside the 1% the ledger comparison allows…
    assert reconcile(Decimal("1008.00"), Decimal("1000.00"), None).ok
    # …and outside what a document's own arithmetic may be out by.
    assert not reconcile(
        Decimal("1008.00"), total=Decimal("1000.00"), tax=None,
        document_total=Decimal("1000.00"),
    ).ok


def test_gross_against_net_is_not_a_disagreement():
    """A German supplier printing VAT-inclusive and a Danish bookkeeper posting
    VAT-exclusive describe one invoice and agree completely.

    Reserving `False` for a real disagreement is the whole value of the flag. One
    that fires on every cross-border invoice is one a reviewer learns to ignore.
    """
    result = reconcile(
        Decimal("104.85"),
        total=Decimal("83.88"),
        tax=Decimal("0.00"),
        document_total=Decimal("104.85"),
        document_subtotal=Decimal("83.88"),
    )

    assert result.ok
    assert result.totals_agree is True


# -- The case that started this ----------------------------------------------


def test_the_aquatuning_invoice_is_accepted():
    """`F10566081`, with its real figures, end to end.

    Three lines printed VAT-inclusive, a shipping charge stated only in the
    totals block, a document total of 104,85 and a Danish posting of 83,88 with
    `tax = 0.00`. Extraction was flawless and the rule rejected it, reporting
    "the extracted lines do not reconcile" over a comparison that was never the
    right one to make.
    """
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
    """The control. Without the document's own figures the same lines are
    rejected — which is what has been happening, and why the invoice still
    stands on an ERP stand-in."""
    lines = Decimal("36.64") + Decimal("31.41") + Decimal("20.90") + Decimal("15.90")

    result = reconcile(lines, Decimal("83.88"), Decimal("0.00"))

    assert not result.ok
