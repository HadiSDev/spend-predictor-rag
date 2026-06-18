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
        matched = m.group(1)
        # If </html> exists in the match, truncate to just after it (inclusive).
        # Otherwise, keep the entire match (to end of string).
        close_tag_idx = matched.lower().rfind("</html>")
        if close_tag_idx != -1:
            matched = matched[:close_tag_idx + len("</html>")]
        return matched.strip()
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
