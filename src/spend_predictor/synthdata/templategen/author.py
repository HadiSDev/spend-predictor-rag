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
