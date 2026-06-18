from pathlib import Path

from spend_predictor.synthdata.templategen import draft


def test_load_exemplar_contains_core_placeholders():
    html = draft.load_exemplar()
    assert "inv.vendor_name" in html
    assert "inv.line_items" in html


def test_build_prompt_includes_exemplar_and_no_real_data_rule():
    prompt = draft.build_prompt("<EXEMPLAR-HTML/>")
    assert "<EXEMPLAR-HTML/>" in prompt
    # The contract and the safety rule must be stated.
    assert "placeholder" in prompt.lower()
    assert "do not" in prompt.lower() or "never" in prompt.lower()


def test_extract_html_from_fenced_block():
    resp = "Here you go:\n```html\n<!DOCTYPE html><html></html>\n```\nDone."
    assert draft.extract_html(resp) == "<!DOCTYPE html><html></html>"


def test_extract_html_bare_doctype():
    resp = "<!DOCTYPE html>\n<html><body>x</body></html>"
    assert draft.extract_html(resp).startswith("<!DOCTYPE html>")


def test_extract_html_returns_none_when_absent():
    assert draft.extract_html("no html here, sorry") is None


def test_draft_template_passes_prompt_and_image_to_generate_fn(tmp_path):
    img = tmp_path / "ref.jpg"
    img.write_bytes(b"img")
    seen = {}

    def fake_generate(prompt, image_path):
        seen["prompt"] = prompt
        seen["image_path"] = image_path
        return "```html\n<!DOCTYPE html><html>{{ inv.vendor_name }}</html>\n```"

    html = draft.draft_template(img, generate_fn=fake_generate)
    assert "inv.vendor_name" in html
    assert seen["image_path"] == img
    # exemplar contract must be in the prompt
    assert "inv.line_items" in seen["prompt"]


def test_draft_template_returns_none_when_no_html(tmp_path):
    img = tmp_path / "ref.jpg"
    img.write_bytes(b"img")
    html = draft.draft_template(img, generate_fn=lambda p, i: "I cannot do that")
    assert html is None


def test_extract_html_bare_strips_trailing_prose():
    resp = "<!DOCTYPE html><html><body>x</body></html>\n\nHope that helps!"
    assert draft.extract_html(resp) == "<!DOCTYPE html><html><body>x</body></html>"
