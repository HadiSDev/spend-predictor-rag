import pytest

from spend_predictor.models import AccountChoice
from spend_predictor.parsing import json_format_hint, parse_model

_CLEAN = (
    '{"account_code":"6010","account_name":"Cloud","level1":"Direct",'
    '"confidence":0.9,"rationale":"ok"}'
)


def test_parse_clean_json():
    c = parse_model(_CLEAN, AccountChoice)
    assert c.account_code == "6010"
    assert c.level1 == "Direct"


def test_parse_fenced_json():
    text = "```json\n" + _CLEAN + "\n```"
    assert parse_model(text, AccountChoice).account_code == "6010"


def test_parse_json_with_surrounding_prose():
    text = "Sure! Here is the categorization:\n" + _CLEAN + "\nLet me know if you need more."
    assert parse_model(text, AccountChoice).confidence == 0.9


def test_parse_repairs_malformed_json():
    # single quotes + trailing comma — invalid JSON that json-repair fixes
    text = (
        "{'account_code': '6010', 'account_name': 'Cloud', 'level1': 'Direct', "
        "'confidence': 0.9, 'rationale': 'ok',}"
    )
    assert parse_model(text, AccountChoice).account_code == "6010"


def test_parse_unwraps_single_nested_object():
    # Model wrapped the answer: {"AccountChoice": {...}} — unwrap the lone value.
    text = '{"AccountChoice": ' + _CLEAN + "}"
    assert parse_model(text, AccountChoice).account_code == "6010"


def test_parse_raises_on_unparseable():
    with pytest.raises(ValueError):
        parse_model("there is no json in this sentence", AccountChoice)


def test_format_hint_is_an_example_not_a_schema():
    # Must show an instance shape, not JSON-Schema metadata the model would echo.
    hint = json_format_hint(AccountChoice)
    assert "account_code" in hint
    assert "Direct | Indirect" in hint  # Literal options rendered for the model
    assert "ONLY" in hint
    assert "properties" not in hint  # not a JSON Schema


def test_format_hint_nested_model_has_line_items_shape():
    from spend_predictor.models import ExtractedInvoice

    hint = json_format_hint(ExtractedInvoice)
    assert "line_items" in hint
    assert "description" in hint  # nested LineItem field appears in the example
