from spend_predictor.synthdata.templategen import validate

GOOD = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  body { font-family: sans-serif; color: #222; }
</style></head><body>
  <div>{{ inv.vendor_name }}</div>
  <div>Billed to {{ buyer_name }}</div>
  {% if extras is defined and extras.po_number %}<div>PO {{ extras.po_number }}</div>{% endif %}
  <table>{% for li in inv.line_items %}<tr><td>{{ li.description }}</td>
  <td>{{ li.amount }}</td></tr>{% endfor %}</table>
  <div>Total {{ inv.total }} {{ inv.currency }}</div>
</body></html>"""


def test_sample_render_inputs_are_deterministic_and_have_lines():
    inv1, buyer1, spec1 = validate.sample_render_inputs()
    inv2, buyer2, spec2 = validate.sample_render_inputs()
    assert inv1.vendor_name == inv2.vendor_name
    assert buyer1 == buyer2
    assert inv1.line_items  # non-empty


def test_good_template_passes_all_checks():
    result = validate.validate_template(GOOD)
    assert result.ok, result.reasons


def test_render_check_fails_on_broken_jinja():
    broken = GOOD.replace("{% endfor %}", "")  # unbalanced tag
    reason = validate.try_render(broken)
    assert reason is not None


def test_contract_check_flags_missing_placeholders():
    no_vendor = GOOD.replace("{{ inv.vendor_name }}", "Acme Corp")
    reasons = validate.contract_check(no_vendor)
    assert any("vendor" in r.lower() for r in reasons)

    no_loop = GOOD.replace("{% for li in inv.line_items %}", "").replace("{% endfor %}", "")
    assert any("line" in r.lower() for r in validate.contract_check(no_loop))


def test_lint_flags_email():
    bad = GOOD.replace("{{ buyer_name }}", "contact@acme.com")
    assert any("email" in r.lower() for r in validate.lint_no_real_data(bad))


def test_lint_flags_long_digit_run():
    bad = GOOD.replace("{{ inv.invoice_number }}", "")  # ensure no placeholder digits
    bad = bad.replace("Billed to {{ buyer_name }}", "Billed to 12345678")
    assert any("digit" in r.lower() for r in validate.lint_no_real_data(bad))


def test_lint_flags_external_image_url():
    bad = GOOD.replace("<body>", '<body><img src="http://logo.example/x.png">')
    assert any("image" in r.lower() or "url" in r.lower()
               for r in validate.lint_no_real_data(bad))


def test_lint_passes_clean_placeholder_template():
    assert validate.lint_no_real_data(GOOD) == []


def test_try_render_writes_preview_pdf(tmp_path):
    out = tmp_path / "preview.pdf"
    reason = validate.try_render(GOOD, out_path=out)
    assert reason is None
    assert out.exists() and out.stat().st_size > 0
