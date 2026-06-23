from pathlib import Path

from spend_predictor.synthdata.templategen import author

GOOD = """<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
  <div>{{ inv.vendor_name }}</div><div>{{ buyer_name }}</div>
  <table>{% for li in inv.line_items %}<tr><td>{{ li.description }}</td>
  <td>{{ li.amount }}</td></tr>{% endfor %}</table>
  <div>Total {{ inv.total }}</div></body></html>"""


def _fake_search(query, n):
    return [f"http://img/{i}.jpg" for i in range(n)]


def _fake_download(url, dest):
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_bytes(b"img")
    return True


def test_author_stages_passing_and_rejected_and_writes_report(tmp_path):
    # First image -> good HTML, second -> a draft that fails lint (an email).
    responses = iter([
        f"```html\n{GOOD}\n```",
        f"```html\n{GOOD.replace('{{ buyer_name }}', 'a@b.com')}\n```",
    ])

    def fake_generate(prompt, image_path):
        return next(responses)

    outcomes = author.author_templates(
        ["eu vat invoice"], tmp_path, n=2,
        search_fn=_fake_search, download_fn=_fake_download, generate_fn=fake_generate,
    )

    assert len(outcomes) == 2
    passed = [o for o in outcomes if o.ok]
    failed = [o for o in outcomes if not o.ok]
    assert len(passed) == 1 and len(failed) == 1
    assert passed[0].html_path.exists()
    assert passed[0].html_path.parent == tmp_path
    assert passed[0].html_path.with_name(passed[0].html_path.stem + ".pdf").exists() \
        or (tmp_path / (passed[0].html_path.stem + ".pdf")).exists()
    assert failed[0].html_path.parent == tmp_path / "_rejected"
    assert (failed[0].html_path.with_suffix(".reason.txt")).exists()
    assert (tmp_path / "report.md").exists()


def test_author_survives_vision_error_on_one_image(tmp_path):
    def fake_generate(prompt, image_path):
        if image_path.name == "0.jpg":
            raise RuntimeError("vision down")
        return f"```html\n{GOOD}\n```"

    outcomes = author.author_templates(
        ["q"], tmp_path, n=2,
        search_fn=_fake_search, download_fn=_fake_download, generate_fn=fake_generate,
    )
    # one image produced no draft (skipped), one produced a passing template
    assert any(o.ok for o in outcomes)
    assert (tmp_path / "report.md").exists()
