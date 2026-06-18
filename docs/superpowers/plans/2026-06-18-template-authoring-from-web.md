# Template Authoring From Web References — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline, human-gated CLI that searches the web for invoice design references, drafts new Jinja2 HTML templates from them via the local vision LLM (no real data), validates them, and stages them for review.

**Architecture:** A new self-contained subpackage `src/spend_predictor/synthdata/templategen/` with four modules — `search` (DuckDuckGo image search + download), `draft` (vision LLM → HTML), `validate` (render + contract + no-real-data lint), `author` (orchestrator + CLI). All network/LLM primitives are module-level defaults injected via parameters, so tests are fully offline. Output goes to a gitignored staging dir; nothing reaches `render/templates/` without a manual move.

**Tech Stack:** Python 3.12, `ddgs` (already a core dep), stdlib `urllib`, Jinja2 + WeasyPrint (already deps), pytest.

## Global Constraints

- **No new dependencies.** `ddgs` is already a core dependency; image download and the vision POST use stdlib `urllib.request`; vision uses the existing `VLLM_BASE_URL` endpoint.
- **No real data in templates, ever.** Generated templates contain only Jinja placeholders for data; no transcribed names/addresses/numbers/emails/logos. Enforced by prompt + lint + human review.
- **Offline by default at runtime.** This tool does NOT touch the generator's runtime path. The generator/scorer keep their current behavior and dependency footprint.
- **Network/LLM via dependency injection.** Default primitives are module-level functions marked `# pragma: no cover`; every public function accepts them as keyword parameters so tests inject fakes (the established pattern in `content.py` and `web_context.py`).
- **Staging only.** The tool writes to `data/template_drafts/` (gitignored). It never writes into `src/spend_predictor/synthdata/render/templates/`.
- **Best-effort per item.** A failed download/draft/render logs and skips that one item; the batch continues.
- Run tests with `uv run pytest`. Python is pinned `>=3.12,<3.13`.

---

### Task 1: Search & download module

**Files:**
- Create: `src/spend_predictor/synthdata/templategen/__init__.py`
- Create: `src/spend_predictor/synthdata/templategen/search.py`
- Test: `tests/synthdata/templategen/test_search.py`
- Create: `tests/synthdata/templategen/__init__.py` (empty, if the test dir needs it — only if sibling test dirs have one; otherwise skip)

**Interfaces:**
- Produces:
  - `PRESETS: dict[str, str]` — preset name → query string.
  - `slug(text: str) -> str` — filesystem-safe slug.
  - `search_references(queries: list[str], out_dir: Path, *, n: int = 5, search_fn: Callable[[str, int], list[str]] = _ddg_image_search, download_fn: Callable[[str, Path], bool] = _download) -> list[Path]` — for each query, search for up to `n` image URLs and download them to `out_dir/_refs/<slug>/<i>.jpg`; returns the list of successfully-downloaded paths. Best-effort.

- [ ] **Step 1: Create the test directory layout and write the failing test**

Create `tests/synthdata/templategen/__init__.py` as an empty file only if `tests/synthdata/` already contains an `__init__.py` (match the existing convention — check with `ls tests/synthdata/`). Then write `tests/synthdata/templategen/test_search.py`:

```python
from pathlib import Path

from spend_predictor.synthdata.templategen import search


def test_presets_are_nonempty_query_strings():
    assert search.PRESETS  # at least one preset
    assert all(isinstance(q, str) and q.strip() for q in search.PRESETS.values())


def test_slug_is_filesystem_safe():
    assert search.slug("EU VAT Invoice!") == "eu-vat-invoice"
    assert search.slug("") == "x"


def test_search_references_downloads_top_n_into_layout(tmp_path):
    calls = {}

    def fake_search(query, n):
        calls["query"] = query
        calls["n"] = n
        return [f"http://img/{i}.jpg" for i in range(n)]

    def fake_download(url, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"img")
        return True

    paths = search.search_references(
        ["eu vat invoice"], tmp_path, n=3,
        search_fn=fake_search, download_fn=fake_download,
    )

    assert calls["n"] == 3
    assert len(paths) == 3
    for p in paths:
        assert p.exists()
        assert p.parent == tmp_path / "_refs" / "eu-vat-invoice"


def test_search_references_skips_failed_downloads(tmp_path):
    def fake_search(query, n):
        return ["http://img/ok.jpg", "http://img/bad.jpg"]

    def fake_download(url, dest):
        if "bad" in url:
            return False
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"img")
        return True

    paths = search.search_references(
        ["q"], tmp_path, n=2, search_fn=fake_search, download_fn=fake_download,
    )
    assert len(paths) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/synthdata/templategen/test_search.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError` (module not created yet).

- [ ] **Step 3: Create the package `__init__.py`**

Create `src/spend_predictor/synthdata/templategen/__init__.py`:

```python
"""Offline tool: web image references -> drafted invoice HTML templates.

Searches the web for invoice design references, drafts Jinja2 templates from them
via the local vision LLM, validates them (render + contract + no-real-data lint),
and stages them for human review. NOT part of the generator's runtime path.
"""
```

- [ ] **Step 4: Implement `search.py`**

Create `src/spend_predictor/synthdata/templategen/search.py`:

```python
"""DuckDuckGo image search + download for invoice design references.

Network primitives are module-level defaults (pragma: no cover); callers inject
fakes in tests. Best-effort: a failed search or download is skipped, never fatal.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

# Preset queries covering the invoice archetypes the generator renders.
PRESETS: dict[str, str] = {
    "eu_vat": "european vat invoice template",
    "us_net30": "us business invoice template net 30",
    "freelancer": "freelancer invoice template",
    "corporate": "corporate invoice template",
    "utility": "utility bill invoice template",
    "saas_receipt": "saas subscription receipt template",
    "minimal": "minimal invoice template",
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def _ddg_image_search(query: str, n: int) -> list[str]:  # pragma: no cover - network
    """Return up to `n` image URLs for `query` via keyless DuckDuckGo image search."""
    try:
        from ddgs import DDGS

        return [r["image"] for r in DDGS().images(query, max_results=n)]
    except Exception:  # noqa: BLE001 - degrade to no results
        return []


def _download(url: str, dest: Path) -> bool:  # pragma: no cover - network
    """Download `url` to `dest`. Return True on success, False on any failure."""
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read()
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except Exception:  # noqa: BLE001 - best-effort
        return False


def search_references(
    queries: list[str], out_dir: Path, *,
    n: int = 5,
    search_fn: Callable[[str, int], list[str]] = _ddg_image_search,
    download_fn: Callable[[str, Path], bool] = _download,
) -> list[Path]:
    """Search each query and download up to `n` images each into
    ``out_dir/_refs/<slug>/<i>.jpg``. Return the downloaded paths."""
    out_dir = Path(out_dir)
    downloaded: list[Path] = []
    for query in queries:
        urls = search_fn(query, n)
        ref_dir = out_dir / "_refs" / slug(query)
        for i, url in enumerate(urls):
            dest = ref_dir / f"{i}.jpg"
            if download_fn(url, dest):
                downloaded.append(dest)
            else:
                log.warning("download failed: %s", url)
    return downloaded
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/synthdata/templategen/test_search.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/spend_predictor/synthdata/templategen/__init__.py \
        src/spend_predictor/synthdata/templategen/search.py \
        tests/synthdata/templategen/
git commit -m "feat(templategen): image search + download with DI"
```

---

### Task 2: Draft module (vision LLM → HTML)

**Files:**
- Create: `src/spend_predictor/synthdata/templategen/draft.py`
- Test: `tests/synthdata/templategen/test_draft.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `load_exemplar() -> str` — returns the contents of `render/templates/minimal.html` (the structural contract exemplar).
  - `build_prompt(exemplar_html: str) -> str` — the instruction text (includes the exemplar and the no-real-data rules).
  - `extract_html(response: str) -> str | None` — extract the HTML from a ```` ```html ```` fenced block (or a bare `<!DOCTYPE`/`<html>` block); `None` if none found.
  - `draft_template(image_path: Path, *, generate_fn: Callable[[str, Path], str], exemplar_html: str | None = None) -> str | None` — call `generate_fn(prompt, image_path)`, return extracted HTML or `None`.

- [ ] **Step 1: Write the failing test**

Create `tests/synthdata/templategen/test_draft.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/synthdata/templategen/test_draft.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `draft.py`**

Create `src/spend_predictor/synthdata/templategen/draft.py`:

```python
"""Draft a Jinja2 invoice template from a reference image via the vision LLM.

The vision call is the module default (pragma: no cover); tests inject a fake
`generate_fn`. The model is told to reproduce layout/styling only and to use the
Jinja placeholders from the exemplar contract — never any real data.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

_EXEMPLAR = Path(__file__).resolve().parents[1] / "render" / "templates" / "minimal.html"


def load_exemplar() -> str:
    """Return the minimal.html template — the structural/placeholder contract."""
    return _EXEMPLAR.read_text(encoding="utf-8")


def build_prompt(exemplar_html: str) -> str:
    return (
        "You are designing a NEW invoice HTML template (Jinja2 + inline CSS) for a "
        "synthetic-data generator. You are shown a reference invoice image.\n\n"
        "RULES:\n"
        "1. Reproduce only the LAYOUT, STRUCTURE, SPACING, COLORS, and TYPOGRAPHY "
        "you see — the visual design.\n"
        "2. NEVER transcribe any real data from the image: no company names, "
        "addresses, numbers, dates, emails, phone numbers, or logos. Every data "
        "slot MUST be a Jinja placeholder.\n"
        "3. Use EXACTLY the same Jinja variables and guards as this reference "
        "template (same variable names; guard optional fields with "
        "`{% if ... is defined %}`):\n\n"
        f"{exemplar_html}\n\n"
        "Output ONLY the complete template inside a single ```html code block. "
        "It must include {{ inv.vendor_name }}, {{ inv.total }}, and a "
        "{% for li in inv.line_items %} loop."
    )


_FENCE_RE = re.compile(r"```html\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_BARE_RE = re.compile(r"(<!DOCTYPE html.*|<html.*)", re.DOTALL | re.IGNORECASE)


def extract_html(response: str) -> str | None:
    """Extract template HTML from a fenced ```html block, else a bare doctype/html."""
    m = _FENCE_RE.search(response)
    if m:
        return m.group(1).strip()
    m = _BARE_RE.search(response)
    if m:
        return m.group(1).strip()
    return None


def _default_vision_generate(prompt: str, image_path: Path) -> str:  # pragma: no cover - live
    """POST the prompt + image to the local OpenAI-compatible vLLM endpoint."""
    import base64
    import json
    import urllib.request

    from ... import config

    b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    body = json.dumps({
        "model": config.VLLM_MODEL.replace("hosted_vllm/", ""),
        "max_tokens": config.VLLM_MAX_TOKENS,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
    }).encode("utf-8")
    req = urllib.request.Request(
        config.VLLM_BASE_URL.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {config.VLLM_API_KEY}"},
    )
    with urllib.request.urlopen(req, timeout=config.VLLM_TIMEOUT) as resp:
        data = json.loads(resp.read())
    return str(data["choices"][0]["message"]["content"])


def draft_template(
    image_path: Path, *,
    generate_fn: Callable[[str, Path], str] = _default_vision_generate,
    exemplar_html: str | None = None,
) -> str | None:
    """Draft a template from `image_path`. Return HTML, or None if none extracted."""
    exemplar_html = load_exemplar() if exemplar_html is None else exemplar_html
    prompt = build_prompt(exemplar_html)
    try:
        response = generate_fn(prompt, image_path)
    except Exception:  # noqa: BLE001 - best-effort
        log.warning("vision generate failed for %s", image_path)
        return None
    html = extract_html(response)
    if html is None:
        log.warning("no HTML in vision response for %s", image_path)
    return html
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/synthdata/templategen/test_draft.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/synthdata/templategen/draft.py \
        tests/synthdata/templategen/test_draft.py
git commit -m "feat(templategen): vision-LLM template drafting with DI"
```

---

### Task 3: Validation module (render + contract + no-real-data lint)

**Files:**
- Create: `src/spend_predictor/synthdata/templategen/validate.py`
- Test: `tests/synthdata/templategen/test_validate.py`

**Interfaces:**
- Consumes: `sampler.sample_plans`, `content.enrich_descriptions`, `models.ExtractedInvoice`, `style.RenderSpec`.
- Produces:
  - `@dataclass ValidationResult: ok: bool; reasons: list[str]`
  - `sample_render_inputs() -> tuple[ExtractedInvoice, str, RenderSpec]` — deterministic `(invoice, buyer_name, render_spec)` built with no LLM (seed 0).
  - `try_render(html: str, out_path: Path | None = None) -> str | None` — render the template string with the sample inputs; write a PDF to `out_path` if given; return `None` on success or an error-reason string on failure.
  - `contract_check(html: str) -> list[str]` — reasons for any missing required placeholder.
  - `lint_no_real_data(html: str) -> list[str]` — reasons for any email / >=4-digit run / external-or-data image URL.
  - `validate_template(html: str) -> ValidationResult` — runs all three; `ok` is True only if all pass.

- [ ] **Step 1: Write the failing test**

Create `tests/synthdata/templategen/test_validate.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/synthdata/templategen/test_validate.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `validate.py`**

Create `src/spend_predictor/synthdata/templategen/validate.py`:

```python
"""Validate a drafted template: renders cleanly + has the contract placeholders
+ contains no real data. Used to gate drafts before a human reviews them."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, select_autoescape

from ...models import ExtractedInvoice
from ..content import enrich_descriptions
from ..sampler import sample_plans
from ..style import RenderSpec


@dataclass
class ValidationResult:
    ok: bool
    reasons: list[str]


def sample_render_inputs() -> tuple[ExtractedInvoice, str, RenderSpec]:
    """Deterministic (invoice, buyer_name, render_spec) for rendering — no LLM."""
    plan = sample_plans(1, seed=0)[0]
    invoice = enrich_descriptions(plan)  # generate_fn=None -> catalog text, no LLM
    return invoice, plan.buyer.name, plan.render


def try_render(html: str, out_path: Path | None = None) -> str | None:
    """Render `html` with the sample inputs. Return None on success, else a reason."""
    invoice, buyer_name, render_spec = sample_render_inputs()
    env = Environment(autoescape=select_autoescape(["html"]))
    try:
        rendered = env.from_string(html).render(
            inv=invoice, buyer_name=buyer_name,
            style=render_spec.style, extras=render_spec,
        )
        from weasyprint import HTML  # local import keeps module light
        pdf = HTML(string=rendered).write_pdf()
        if out_path is not None:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(pdf)
    except Exception as exc:  # noqa: BLE001 - reason is the message
        return f"render failed: {exc}"
    return None


def contract_check(html: str) -> list[str]:
    """Reasons for any missing required placeholder."""
    reasons: list[str] = []
    if "inv.vendor_name" not in html:
        reasons.append("missing vendor placeholder {{ inv.vendor_name }}")
    if "inv.total" not in html:
        reasons.append("missing total placeholder {{ inv.total }}")
    if not re.search(r"{%\s*for\s+\w+\s+in\s+inv\.line_items", html):
        reasons.append("missing line-item loop {% for li in inv.line_items %}")
    return reasons


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_DIGITS_RE = re.compile(r"\d{4,}")
_IMG_URL_RE = re.compile(r"""(src\s*=\s*['"]\s*https?:|url\(\s*['"]?\s*https?:|data:image)""",
                         re.IGNORECASE)
_STYLE_RE = re.compile(r"<style.*?</style>", re.DOTALL | re.IGNORECASE)
_JINJA_RE = re.compile(r"{{.*?}}|{%.*?%}", re.DOTALL)


def lint_no_real_data(html: str) -> list[str]:
    """Reasons for any sign of copied real data."""
    reasons: list[str] = []
    # Image-URL / embedded-logo check runs on the FULL html (CSS included).
    if _IMG_URL_RE.search(html):
        reasons.append("external or data: image URL (possible real logo)")
    # Email / digit checks run on visible text only: strip <style> and Jinja tags
    # so CSS pixel values and placeholder expressions don't false-positive.
    text = _JINJA_RE.sub(" ", _STYLE_RE.sub(" ", html))
    if _EMAIL_RE.search(text):
        reasons.append("email address in template text")
    if _DIGITS_RE.search(text):
        reasons.append("run of >=4 digits in template text (possible real number)")
    return reasons


def validate_template(html: str) -> ValidationResult:
    """Run render + contract + lint. ok only if all pass."""
    reasons: list[str] = []
    render_reason = try_render(html)
    if render_reason is not None:
        reasons.append(render_reason)
    reasons.extend(contract_check(html))
    reasons.extend(lint_no_real_data(html))
    return ValidationResult(ok=not reasons, reasons=reasons)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/synthdata/templategen/test_validate.py -v`
Expected: PASS (9 tests). If `test_lint_flags_long_digit_run` is brittle because `GOOD` lacks an `inv.invoice_number` token, note the test already removes that token first; the assertion only fires on the injected `12345678`.

- [ ] **Step 5: Commit**

```bash
git add src/spend_predictor/synthdata/templategen/validate.py \
        tests/synthdata/templategen/test_validate.py
git commit -m "feat(templategen): render/contract/no-real-data validation"
```

---

### Task 4: Orchestrator, CLI, gitignore & docs

**Files:**
- Create: `src/spend_predictor/synthdata/templategen/author.py`
- Create: `src/spend_predictor/synthdata/templategen/__main__.py`
- Modify: `.gitignore` (add `data/template_drafts/`)
- Modify: `README.md` (document the tool under the synthetic-data section)
- Test: `tests/synthdata/templategen/test_author.py`

**Interfaces:**
- Consumes: `search.search_references`, `draft.draft_template`, `validate.validate_template`, `validate.try_render`.
- Produces:
  - `@dataclass DraftOutcome: name: str; ok: bool; reasons: list[str]; html_path: Path`
  - `author_templates(queries: list[str], out_dir: Path, *, n: int = 5, search_fn=search._ddg_image_search, download_fn=search._download, generate_fn=draft._default_vision_generate) -> list[DraftOutcome]`
  - `main(argv: list[str] | None = None) -> int` — CLI entry.

- [ ] **Step 1: Write the failing test**

Create `tests/synthdata/templategen/test_author.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/synthdata/templategen/test_author.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `author.py`**

Create `src/spend_predictor/synthdata/templategen/author.py`:

```python
"""Orchestrate: search -> draft -> validate -> stage drafts for human review.

Writes passing templates to ``out_dir/<name>.html`` (+ a ``<name>.pdf`` preview),
failing ones to ``out_dir/_rejected/<name>.html`` (+ ``<name>.reason.txt``), and a
``report.md`` summary. Nothing is written into render/templates/ — a human moves
approved templates over manually.
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import draft, search, validate

log = logging.getLogger(__name__)


@dataclass
class DraftOutcome:
    name: str
    ok: bool
    reasons: list[str]
    html_path: Path


def _name_for(ref: Path) -> str:
    # ref is out_dir/_refs/<query-slug>/<i>.jpg  ->  "<query-slug>-<i>"
    return f"{ref.parent.name}-{ref.stem}"


def author_templates(
    queries: list[str], out_dir: Path, *,
    n: int = 5,
    search_fn: Callable[[str, int], list[str]] = search._ddg_image_search,
    download_fn: Callable[[str, Path], bool] = search._download,
    generate_fn: Callable[[str, Path], str] = draft._default_vision_generate,
) -> list[DraftOutcome]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir = out_dir / "_rejected"

    refs = search.search_references(
        queries, out_dir, n=n, search_fn=search_fn, download_fn=download_fn,
    )
    exemplar = draft.load_exemplar()
    outcomes: list[DraftOutcome] = []

    for ref in refs:
        name = _name_for(ref)
        html = draft.draft_template(ref, generate_fn=generate_fn, exemplar_html=exemplar)
        if html is None:
            log.warning("no draft produced for %s; skipping", ref)
            continue
        result = validate.validate_template(html)
        if result.ok:
            html_path = out_dir / f"{name}.html"
            html_path.write_text(html, encoding="utf-8")
            validate.try_render(html, out_path=out_dir / f"{name}.pdf")
        else:
            rejected_dir.mkdir(parents=True, exist_ok=True)
            html_path = rejected_dir / f"{name}.html"
            html_path.write_text(html, encoding="utf-8")
            (rejected_dir / f"{name}.reason.txt").write_text(
                "\n".join(result.reasons), encoding="utf-8")
        outcomes.append(DraftOutcome(name, result.ok, result.reasons, html_path))

    _write_report(out_dir, outcomes)
    return outcomes


def _write_report(out_dir: Path, outcomes: list[DraftOutcome]) -> None:
    lines = ["# Template draft report", ""]
    passed = [o for o in outcomes if o.ok]
    lines.append(f"{len(passed)}/{len(outcomes)} drafts passed validation.")
    lines.append("")
    for o in outcomes:
        status = "PASS" if o.ok else "FAIL"
        lines.append(f"- **{status}** `{o.name}` -> `{o.html_path}`")
        for r in o.reasons:
            lines.append(f"  - {r}")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Draft invoice HTML templates from web image references.")
    parser.add_argument("--query", action="append", default=None,
                        help="Search query (repeatable). Defaults to built-in presets.")
    parser.add_argument("--n", type=int, default=5, help="Images per query.")
    parser.add_argument("--out", default="data/template_drafts",
                        help="Output staging directory.")
    args = parser.parse_args(argv)

    queries = args.query if args.query else list(search.PRESETS.values())
    outcomes = author_templates(queries, Path(args.out), n=args.n)
    passed = sum(1 for o in outcomes if o.ok)
    log.info("Done: %d/%d drafts passed. Review %s and move keepers into "
             "render/templates/.", passed, len(outcomes), args.out)
    return 0
```

- [ ] **Step 4: Implement `__main__.py`**

Create `src/spend_predictor/synthdata/templategen/__main__.py`:

```python
import sys

from .author import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/synthdata/templategen/test_author.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Add the staging dir to .gitignore**

Append to `.gitignore` (confirm the line isn't already present):

```
data/template_drafts/
```

- [ ] **Step 7: Document the tool in README.md**

In `README.md`, under the "## Synthetic data & benchmarking" section, after the "### Generate synthetic invoices" subsection, add:

```markdown
### Author new templates from web references (optional)

Grow the template library by drafting new templates from real invoice *designs*
found online. This is an offline developer tool — separate from the generator —
and is **human-gated**: it stages drafts for you to review, and never writes into
`render/templates/` itself.

\`\`\`bash
uv run python -m spend_predictor.synthdata.templategen --n 5
# or drive the search yourself:
uv run python -m spend_predictor.synthdata.templategen --query "eu vat invoice template" --n 8
\`\`\`

It searches DuckDuckGo images (no key), drafts a Jinja2 template per image via the
local **vision** LLM (requires your vLLM server to serve the model with vision
enabled), then validates each draft — it must render cleanly, contain the required
placeholders, and pass a **no-real-data lint** (no emails, long digit runs, or
embedded image URLs). Results land in `data/template_drafts/` (gitignored):
passing drafts as `<name>.html` + `<name>.pdf` preview, failures under
`_rejected/` with a reason, plus a `report.md`. Review them, then move the good
`.html` files into `src/spend_predictor/synthdata/render/templates/` — the
generator auto-discovers them.

**No real data ever enters a template:** the vision model is instructed to copy
only layout/styling and use Jinja placeholders for all data; the lint and your
manual review are the backstops.
```

(Replace the `\`\`\`` escapes with real triple-backtick fences when editing.)

- [ ] **Step 8: Run the whole suite**

Run: `uv run pytest`
Expected: PASS — the prior 115 tests plus the new templategen tests (≈22 new).

- [ ] **Step 9: Commit**

```bash
git add src/spend_predictor/synthdata/templategen/author.py \
        src/spend_predictor/synthdata/templategen/__main__.py \
        tests/synthdata/templategen/test_author.py .gitignore README.md
git commit -m "feat(templategen): orchestrator + CLI, gitignore staging, docs"
```

---

## Notes for the implementer

- Match the existing test layout: tests live under `tests/synthdata/...`. Check whether `tests/synthdata/` uses `__init__.py` files and mirror that for `tests/synthdata/templategen/`.
- The vision/network defaults (`_ddg_image_search`, `_download`, `_default_vision_generate`) are `# pragma: no cover` — never exercised by tests, only by real CLI runs.
- Do not import `weasyprint` at module top level in `validate.py`; import it inside `try_render` (mirrors `renderer.py`, keeps module import light).
- `sample_render_inputs()` calls `sample_plans(1, seed=0)` which reads `data/chart_of_accounts.csv` from disk — that file exists in the repo, so the validator works offline with no fixtures.
