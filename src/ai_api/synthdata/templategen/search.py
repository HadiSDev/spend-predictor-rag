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
