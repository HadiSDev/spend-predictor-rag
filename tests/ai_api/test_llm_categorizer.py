"""Categorizing one invoice line by asking a model.

The keyword matcher this replaces scored token overlap between a description and
an English leaf name. On real Danish ledger data that scored zero on almost
everything, and its one "success" was `Company Free plan fee` -> Telecom,
because `plan` is a telecom keyword. A wrong category is worse than an honest
backlog, which is why there is no keyword fallback here.

Every test drives the model through the `complete` seam, so the suite needs no
model running and asserts on our prompt and our grounding, never on a mock's
behaviour.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from ai_api.sync.categorizer import Category
from ai_api.sync.llm_categorizer import (
    CategorizerUnavailable,
    LineContext,
    build_prompt,
    categorize_line,
)

SOFTWARE = Category(
    node_id="n-software",
    path=("Indirect", "Technology", "Software"),
    name="Software",
    code="6020",
    description="Licences and subscriptions",
)
TRAVEL = Category(
    node_id="n-travel",
    path=("Indirect", "Travel", "Airfare"),
    name="Airfare",
    code="6800",
    description="Flights and rail",
)
CANDIDATES = [SOFTWARE, TRAVEL]


def replying(text: str):
    """A model that always answers `text`, recording the prompt it was given."""
    seen: list[str] = []

    def complete(prompt: str) -> str:
        seen.append(prompt)
        return text

    complete.prompts = seen  # type: ignore[attr-defined]
    return complete


def test_the_chosen_candidate_becomes_the_categorization():
    complete = replying('{"choice": 1, "confidence": 0.82, "rationale": "A licence."}')

    match = categorize_line(
        LineContext(item_name="Claude Code"), CANDIDATES, complete=complete
    )

    assert match.matched
    # The node's own id, so a match cannot land on a real node and still store a
    # null pointer — the same rule the keyword matcher followed.
    assert match.spend_category_id == "n-software"
    assert (match.level_1, match.level_2, match.level_3) == (
        "Indirect", "Technology", "Software",
    )
    assert match.level_4 is None
    assert match.account_code == "6020"
    assert match.account_name == "Software"
    assert match.confidence == 0.82
    assert match.rationale == "A licence."


def test_a_second_choice_is_not_confused_with_the_first():
    complete = replying('{"choice": 2, "confidence": 0.7, "rationale": "A train ticket."}')

    match = categorize_line(
        LineContext(item_name="Togbillet"), CANDIDATES, complete=complete
    )

    assert match.spend_category_id == "n-travel"
    assert match.level_3 == "Airfare"


def test_the_model_may_decline():
    """Declining is a real answer, not a failure to extract one.

    A model forced to pick from a tree that has no home for a line is how
    `Company Free plan fee` became Telecom.
    """
    complete = replying(
        '{"choice": 0, "confidence": 0.0, "rationale": "No candidate covers bank fees."}'
    )

    match = categorize_line(
        LineContext(item_name="Revolut Business Fee"), CANDIDATES, complete=complete
    )

    assert not match.matched
    assert match.spend_category_id is None
    assert match.level_1 is None
    assert "bank fees" in match.rationale


def test_a_choice_outside_the_candidate_list_is_refused_not_snapped():
    """Grounding: an index we did not offer resolves to nothing.

    Snapping to the nearest candidate would turn a model that misread the list
    into a confident wrong answer, which is exactly the failure mode this
    replaces.
    """
    complete = replying('{"choice": 7, "confidence": 0.9, "rationale": "Confident."}')

    match = categorize_line(
        LineContext(item_name="Kamera"), CANDIDATES, complete=complete
    )

    assert not match.matched
    assert match.spend_category_id is None
    assert "7" in match.rationale


def test_the_prompt_carries_what_a_bookkeeper_would_use():
    """Not just the description — half of Billy's lines have none at all."""
    complete = replying('{"choice": 1, "confidence": 0.5, "rationale": "ok"}')

    categorize_line(
        LineContext(
            item_name="",
            native_account_code="1835",
            native_account_name="Edb-udgifter / software",
            supplier="Anthropic, PBC",
            amount=Decimal("672.83"),
            currency="DKK",
        ),
        CANDIDATES,
        complete=complete,
    )

    prompt = complete.prompts[0]
    assert "1835" in prompt
    assert "Edb-udgifter / software" in prompt
    assert "Anthropic, PBC" in prompt
    assert "672.83" in prompt
    assert "DKK" in prompt


def test_the_prompt_offers_every_candidate_with_its_full_path():
    complete = replying('{"choice": 1, "confidence": 0.5, "rationale": "ok"}')

    categorize_line(LineContext(item_name="x"), CANDIDATES, complete=complete)

    prompt = complete.prompts[0]
    assert "Indirect > Technology > Software" in prompt
    assert "Indirect > Travel > Airfare" in prompt
    # Numbered, because the model answers with an index: no name matching, so a
    # near-miss on spelling cannot become a near-miss on category.
    assert "1." in prompt and "2." in prompt


def test_language_is_not_the_models_problem():
    """A Danish description is categorized like any other — the whole point."""
    complete = replying('{"choice": 2, "confidence": 0.77, "rationale": "Togbillet = train ticket."}')

    match = categorize_line(
        LineContext(item_name="Togbillet", native_account_name="Transport and Travel"),
        CANDIDATES,
        complete=complete,
    )

    assert match.matched
    assert match.level_3 == "Airfare"


def test_no_candidates_means_no_call_and_no_guess():
    """No tree, no categorization — and no tokens spent discovering that."""
    complete = replying('{"choice": 1, "confidence": 1.0, "rationale": "never asked"}')

    match = categorize_line(LineContext(item_name="x"), [], complete=complete)

    assert not match.matched
    assert complete.prompts == []


def test_an_unreachable_model_is_not_a_failed_line():
    """Distinguishing "the model said no" from "there was no model".

    An outage that marked lines `ai_failed` would bury a batch behind a status
    the sync never retries; left uncategorized they are picked up next run.
    """
    def complete(prompt: str) -> str:
        raise ConnectionError("connection refused")

    with pytest.raises(CategorizerUnavailable):
        categorize_line(LineContext(item_name="x"), CANDIDATES, complete=complete)


def test_an_unparseable_reply_is_treated_as_an_outage():
    """Garbage means the serving stack is wrong, not that this line is hard."""
    complete = replying("I'm sorry, I can't help with that.")

    with pytest.raises(CategorizerUnavailable):
        categorize_line(LineContext(item_name="x"), CANDIDATES, complete=complete)


def test_a_fenced_reply_still_parses():
    """Models fence JSON whatever the instruction says."""
    complete = replying(
        '```json\n{"choice": 1, "confidence": 0.6, "rationale": "fenced"}\n```'
    )

    match = categorize_line(LineContext(item_name="x"), CANDIDATES, complete=complete)

    assert match.matched
    assert match.rationale == "fenced"


def test_confidence_is_clamped_to_a_probability():
    """A model that answers 95 rather than 0.95 must not store 95.0."""
    complete = replying('{"choice": 1, "confidence": 95, "rationale": "ok"}')

    match = categorize_line(LineContext(item_name="x"), CANDIDATES, complete=complete)

    assert 0.0 <= match.confidence <= 1.0


def test_the_prompt_is_built_without_calling_anything():
    """`build_prompt` is public so a prompt change is reviewable on its own."""
    prompt = build_prompt(LineContext(item_name="Kamera"), CANDIDATES)

    assert "Kamera" in prompt
    assert "Software" in prompt


# --- The accounting judgements the prompt has to carry ----------------------
#
# A line's wording points at the wrong answer often enough that a categorizer
# reading it literally is wrong in predictable, repeatable ways: an
# environmental levy on a haulier's invoice reads as logistics, a pallet from a
# machine-tool supplier reads as machinery, a laptop inside a consulting
# engagement reads as hardware. These assert the rules are *stated*, which is
# all a prompt can be tested for offline — whether the model obeys them is what
# the corpus run in phase 1.7 measures.


def _prompt_for(**context) -> str:
    return build_prompt(LineContext(**context), CANDIDATES)


def test_a_fee_outranks_the_supplier_that_issued_it():
    prompt = _prompt_for(item_name="Miljøtillæg", supplier="DSV Road A/S")

    assert "fees and taxes REGARDLESS of which supplier issued it" in prompt


def test_freight_is_excluded_from_the_fee_rule():
    """Named explicitly because "tillæg", "surcharge" and "fee" appear on almost
    every freight invoice, and the fee rule would otherwise swallow logistics."""
    assert "Freight and shipping are NOT" in _prompt_for(item_name="Fragt")


def test_packaging_outranks_the_supplier():
    assert "Packaging" in _prompt_for(item_name="Paller")


def test_a_product_inside_a_service_follows_the_service():
    prompt = _prompt_for(item_name="MacBook Pro", supplier="Nordic Design Studio")

    assert "follows the SERVICE, not the product" in prompt


def test_a_bare_discount_follows_the_supplier():
    assert "discount or rebate is categorized from the supplier" in _prompt_for(
        item_name="Rabat"
    )


# --- Reasoning before the answer -------------------------------------------


def test_the_prompt_invites_reasoning_before_the_json():
    """The shared JSON hint forbids commentary; this prompt opts out of that ban.

    Choosing one of forty categories is a judgement, not a transcription, and
    the two other `json_format_hint` callers — invoice extraction and page
    reading — are transcriptions where reasoning is pure latency.
    """
    prompt = _prompt_for(item_name="Kamera")

    assert "Think it through first" in prompt
    assert "no commentary before or after" not in prompt


def test_prose_before_the_json_still_parses():
    complete = replying(
        "Both Software and Airfare are plausible here. The line names a camera, "
        "which is neither a licence nor a journey, but Software is the closer of "
        "the two given the ledger account.\n"
        '{"choice": 1, "confidence": 0.4, "rationale": "Closest of a poor pair."}'
    )

    match = categorize_line(LineContext(item_name="Kamera"), CANDIDATES, complete=complete)

    assert match.matched and match.account_code == "6020"
    assert match.confidence == 0.4


def test_a_fenced_object_after_reasoning_still_parses():
    """Small models fence their JSON however firmly they are told not to."""
    complete = replying(
        "Reasoning: this is a licence.\n```json\n"
        '{"choice": 1, "confidence": 0.9, "rationale": "A licence."}\n```'
    )

    match = categorize_line(LineContext(item_name="Claude"), CANDIDATES, complete=complete)

    assert match.matched and match.account_code == "6020"
