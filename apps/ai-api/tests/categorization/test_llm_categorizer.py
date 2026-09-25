"""Categorizing one invoice line by asking a model."""
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


def test_the_model_must_answer_and_is_told_so():
    prompt = build_prompt(LineContext(item_name="Revolut Business Fee"), CANDIDATES)

    assert "0. None of these fit" not in prompt
    assert "must" in prompt.lower()
    assert "estimate" in prompt.lower()


def test_a_zero_answer_is_an_index_we_never_offered():
    complete = replying(
        '{"choice": 0, "confidence": 0.0, "rationale": "No candidate covers bank fees."}'
    )

    match = categorize_line(
        LineContext(item_name="Revolut Business Fee"), CANDIDATES, complete=complete
    )

    assert not match.matched
    assert match.spend_category_id is None
    assert "0" in match.rationale


def test_a_choice_outside_the_candidate_list_is_refused_not_snapped():
    complete = replying('{"choice": 7, "confidence": 0.9, "rationale": "Confident."}')

    match = categorize_line(
        LineContext(item_name="Kamera"), CANDIDATES, complete=complete
    )

    assert not match.matched
    assert match.spend_category_id is None
    assert "7" in match.rationale


def test_the_prompt_carries_what_a_bookkeeper_would_use():
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
    assert "1." in prompt and "2." in prompt


def test_language_is_not_the_models_problem():
    complete = replying('{"choice": 2, "confidence": 0.77, "rationale": "Togbillet = train ticket."}')

    match = categorize_line(
        LineContext(item_name="Togbillet", native_account_name="Transport and Travel"),
        CANDIDATES,
        complete=complete,
    )

    assert match.matched
    assert match.level_3 == "Airfare"


def test_no_candidates_means_no_call_and_no_guess():
    complete = replying('{"choice": 1, "confidence": 1.0, "rationale": "never asked"}')

    match = categorize_line(LineContext(item_name="x"), [], complete=complete)

    assert not match.matched
    assert complete.prompts == []


def test_an_unreachable_model_is_not_a_failed_line():
    def complete(prompt: str) -> str:
        raise ConnectionError("connection refused")

    with pytest.raises(CategorizerUnavailable):
        categorize_line(LineContext(item_name="x"), CANDIDATES, complete=complete)


def test_an_unparseable_reply_is_treated_as_an_outage():
    complete = replying("I'm sorry, I can't help with that.")

    with pytest.raises(CategorizerUnavailable):
        categorize_line(LineContext(item_name="x"), CANDIDATES, complete=complete)


def test_a_fenced_reply_still_parses():
    complete = replying(
        '```json\n{"choice": 1, "confidence": 0.6, "rationale": "fenced"}\n```'
    )

    match = categorize_line(LineContext(item_name="x"), CANDIDATES, complete=complete)

    assert match.matched
    assert match.rationale == "fenced"


def test_confidence_is_clamped_to_a_probability():
    complete = replying('{"choice": 1, "confidence": 95, "rationale": "ok"}')

    match = categorize_line(LineContext(item_name="x"), CANDIDATES, complete=complete)

    assert 0.0 <= match.confidence <= 1.0


def test_the_prompt_is_built_without_calling_anything():
    prompt = build_prompt(LineContext(item_name="Kamera"), CANDIDATES)

    assert "Kamera" in prompt
    assert "Software" in prompt


def _prompt_for(**context) -> str:
    return build_prompt(LineContext(**context), CANDIDATES)


def _facts_of(**context) -> str:
    """Only the block describing the line."""
    prompt = _prompt_for(**context)
    return prompt.split("Invoice line:\n", 1)[1].split("\n\nCategories:", 1)[0]


def test_a_fee_outranks_the_supplier_that_issued_it():
    prompt = _prompt_for(item_name="Miljøtillæg", supplier="DSV Road A/S")

    assert "fees and taxes REGARDLESS of which supplier issued it" in prompt


def test_freight_is_excluded_from_the_fee_rule():
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


def test_the_prompt_invites_reasoning_before_the_json():
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
    complete = replying(
        "Reasoning: this is a licence.\n```json\n"
        '{"choice": 1, "confidence": 0.9, "rationale": "A licence."}\n```'
    )

    match = categorize_line(LineContext(item_name="Claude"), CANDIDATES, complete=complete)

    assert match.matched and match.account_code == "6020"


def test_a_described_supplier_qualifies_its_own_name():
    prompt = _prompt_for(
        item_name="1 Voksen",
        supplier="DSB",
        supplier_description="Danish State Railways, passenger rail operator.",
    )

    assert "Supplier: DSB — Danish State Railways, passenger rail operator." in prompt


def test_an_undescribed_supplier_states_only_its_name():
    facts = _facts_of(item_name="1 Voksen", supplier="DSB")

    assert "Supplier: DSB" in facts
    assert "—" not in facts, "no dangling qualifier where there is nothing to qualify"


def test_the_buyer_is_named():
    prompt = _prompt_for(item_name="MacBook Pro", buyer="VectorLab ApS")

    assert "Bought by: VectorLab ApS" in prompt
