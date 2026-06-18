# Template Authoring From Web References — Design

**Date:** 2026-06-18
**Status:** Approved (design); pending spec review before planning.

## Goal

Build an **offline, human-gated CLI tool** that searches the internet for invoice
design references, uses the **local vision LLM** to draft new Jinja2 HTML invoice
templates (visually inspired by the references, containing **no real data**),
validates them, and **stages** them for human review. Approved templates are
moved by hand into `src/spend_predictor/synthdata/render/templates/`, where the
generator's existing auto-discovery (`list_templates()`) picks them up with zero
code change.

The purpose is to grow the synthetic generator's template library (currently 9
templates) with more, visually-diverse layouts — addressing the standing quality
bar that the data must have strong layout variation (see
`synthdata-variation-bar`).

## Core boundaries (decided in brainstorming)

1. **Real invoices as design *reference only*.** Real invoices may inform layout,
   structure, spacing, color, and typography. **No real data** — names,
   addresses, VAT numbers, amounts, emails, logos, or any transcribed text — ever
   lands in a generated template. Every data slot is a Jinja placeholder.
2. **Offline authoring tool, not a runtime step.** The generator stays exactly as
   it is: deterministic and offline-by-default. All network + vision-LLM activity
   lives in this separate tool, run occasionally by a developer.
3. **Local vision LLM** does the image → HTML drafting. The project's local vLLM
   serves `google/gemma-4-E4B-it` with vision enabled (verified: the
   `/v1/chat/completions` endpoint accepts `image_url` content and describes
   images). No external API, no key — consistent with the project's self-hosted
   ethos.
4. **DuckDuckGo image search** (`ddgs`, no key) for the search step — consistent
   with the existing DuckDuckGo web-context usage. Query presets plus a
   `--query` override; DDG's noisy results are acceptable because a human reviews
   every draft before anything is committed.

## Architecture — new subpackage `src/spend_predictor/synthdata/templategen/`

Completely separate from the generator's runtime path. Four focused modules plus
a CLI.

### `search.py` — image search + download
- DuckDuckGo image search via `ddgs`, injected as a client so tests stub it.
- Built-in **query presets** (e.g. `eu_vat`, `us_net30`, `freelancer`, `utility`,
  `receipt`) plus a `--query` free-form override.
- Downloads top-N images per query into a gitignored staging layout:
  `data/template_drafts/_refs/<query>/<n>.jpg`.
- Best-effort per item: a failed download logs and is skipped; the run continues.

### `draft.py` — vision LLM → HTML
- For each downloaded reference image, send to the local vLLM:
  `(reference image) + (an existing template as the structural contract/exemplar)
  + (instructions)`.
- Instructions: reproduce **layout/structure/spacing/color/typography only**;
  never transcribe any name, address, number, email, or logo from the image;
  every data slot must be a Jinja placeholder from the provided contract; guard
  optional fields with `{% if ... is defined %}` (matching existing templates).
- Extract the HTML from a fenced ```` ```html ```` code block in the response.
- The vision call is injected as a `generate_fn` (same DI pattern as
  `content.py`'s `enrich_descriptions`), so tests run offline.
- A response with no extractable HTML block logs and is skipped (not a crash).

### `validate.py` — the safety + quality gate
Three checks; a draft must pass all three to be staged (otherwise it is moved to
`_rejected/` with a written reason):
1. **Render check** — renders cleanly through the existing
   `render.renderer.render_invoice_pdf` with a sample `ExtractedInvoice` (catches
   broken Jinja/CSS).
2. **Contract check** — the template contains the required placeholders: the
   vendor field, the total field, and a line-item loop (`{% for ... %}`), and uses
   `{% if ... is defined %}` guards for optional fields.
3. **No-real-data lint** — rejects/flags a draft whose source contains an email
   pattern, a run of >= 4 consecutive digits (amounts/VAT/phone), or an external
   or `data:` image URL (which would smuggle a real logo). These signal copied
   real data.

### `author.py` / `__main__` — orchestrator + CLI
Pipeline: `search -> download -> draft -> validate -> stage`. CLI:
`python -m spend_predictor.synthdata.templategen --query "..." --n 5 --out data/template_drafts`
(presets used when no `--query` given). Writes:
- `data/template_drafts/<query>-<n>.html` + `preview.pdf` + a copy of the ref, for
  each PASS;
- `data/template_drafts/_rejected/<...>.html` + `reason.txt` for each FAIL;
- `data/template_drafts/report.md` summarizing every draft (ref, render status,
  lint notes).

## Data flow

```
preset queries (+ --query)
  |- ddgs image search -> download top-N -> data/template_drafts/_refs/<query>/<n>.jpg
        |- for each ref image:
             vision LLM(ref image + exemplar template + contract) -> extract ```html block
                |- validate (render + contract + no-real-data lint)
                     |- PASS -> data/template_drafts/<query>-<n>.html + preview.pdf + ref copy
                     |- FAIL -> data/template_drafts/_rejected/<...>.html + reason.txt
        |- write report.md
human reviews template_drafts/ -> moves keepers into render/templates/ -> auto-discovered
```

## No-real-data guarantee — three layers

1. **Prompt** — explicit instruction to reproduce layout/styling only and use
   Jinja placeholders for every data slot.
2. **Lint** — automated rejection on email patterns, >= 4-digit runs, and
   external/`data:` image URLs.
3. **Human review gate** — nothing reaches `render/templates/` (and thus the
   public repo) without an explicit manual move.

## Dependencies

- `ddgs` — DuckDuckGo image search (no key).
- HTTP download via the client already used by the project's web-context code
  (no new HTTP dependency if avoidable).
- Vision via the existing OpenAI-compatible endpoint — **no new model dependency**.

These are tooling-only; they belong in a **new optional `templategen` dependency
group** (`uv sync --group templategen`) — kept separate from both the core
runtime and the `live` (Curator) group, so the generator and scorer keep their
current dependency footprint and nobody installs `ddgs` just to score.

## Error handling

- Best-effort per item throughout (matches `generate.py`): a failed download,
  empty/unparseable vision response, or render error logs the reason, skips that
  one image, and the batch continues.
- Validation failures are *recorded* (moved to `_rejected/` with a reason), not
  fatal.

## Testing (all offline; network + LLM injected via DI)

- **search:** stub the `ddgs` client to return fixed URLs and stub the
  downloader; assert images land in `_refs/<query>/<n>.jpg` and N is respected; a
  download error skips that URL without aborting.
- **draft:** inject a fake `generate_fn` returning a known ```` ```html ```` block;
  assert correct extraction; assert a no-code-fence response is skipped (logged,
  not a crash); assert the exemplar template + contract are present in the prompt
  passed to `generate_fn`.
- **validate** (most coverage — safety-critical):
  - a known-good template passes all three checks;
  - a template that throws on render fails the render check;
  - a template missing vendor/total/line-loop placeholders fails the contract
    check;
  - lint rejects drafts containing an email, a >= 4-digit run, and an
    external/`data:` image URL (one test each);
  - a clean placeholder-only template passes lint.
- **author orchestrator:** end-to-end with stubbed search + stubbed vision;
  passing drafts go to `template_drafts/`, failing ones to `_rejected/` with a
  reason, and `report.md` is written; a vision error on one image does not abort
  the batch.

## Out of scope

- No changes to the generator's runtime path, the scorer, or the live data model.
- No automatic commit of templates — staging + manual move only.
- No image-fixture generation or OCR (that remains Phase 2 of the generator spec).
- The vision model's drafts are starting points; hand-polishing a staged template
  before moving it is expected and out of the tool's responsibility.
