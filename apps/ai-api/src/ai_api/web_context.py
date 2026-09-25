"""External web context for categorization: buyer-website scrape + product search."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Callable

from crewai_tools import ScrapeWebsiteTool
from ddgs import DDGS

from . import config


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def _cache_path(cache_dir: str, key: str) -> Path:
    slug = _slug(key)[:120]
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return Path(cache_dir) / f"{slug}-{digest}.txt"


def _read_cache(cache_dir: str, key: str) -> str | None:
    path = _cache_path(cache_dir, key)
    return path.read_text(encoding="utf-8") if path.exists() else None


def _write_cache(cache_dir: str, key: str, value: str) -> None:
    path = _cache_path(cache_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _scrape(url: str) -> str:
    """Scrape a website's text with CrewAI's keyless ScrapeWebsiteTool."""
    try:
        return ScrapeWebsiteTool(website_url=url).run() or ""
    except Exception:  # noqa: BLE001
        return ""


def _ddg_search(query: str) -> list[dict]:
    """Keyless DuckDuckGo text search; returns [{title, body, href}, ...]."""
    try:
        return list(DDGS().text(query, max_results=config.PRODUCT_SEARCH_MAX_RESULTS))
    except Exception:  # noqa: BLE001
        return []


def _summarize_buyer(name: str, text: str) -> str:
    if not text.strip():
        return f"No website context available for '{name}'."
    prompt = (
        f"In 2-3 sentences, describe the business of '{name}' based on this website "
        f"text: what they make/sell and how they earn revenue.\n\n{text[:6000]}"
    )
    try:
        return config.get_llm().call(messages=[{"role": "user", "content": prompt}]).strip()
    except Exception:  # noqa: BLE001
        return f"No website context available for '{name}'."


def _summarize_products(items_with_snippets: list[tuple[str, str]]) -> str:
    blob = "\n\n".join(f"ITEM: {desc}\nSNIPPETS: {snip}" for desc, snip in items_with_snippets)
    prompt = (
        "For each invoice line item below, write one short line stating what the "
        "product/service is (use the snippets; if unclear, say 'unclear').\n\n" + blob
    )
    try:
        return config.get_llm().call(messages=[{"role": "user", "content": prompt}]).strip()
    except Exception:  # noqa: BLE001
        return "PRODUCTS:\n" + "\n".join(f"- {d}: {s}" for d, s in items_with_snippets)


def get_buyer_context(
    name: str | None = None,
    website: str | None = None,
    *,
    scrape_fn: Callable[[str], str] = _scrape,
    summarize_fn: Callable[[str, str], str] = _summarize_buyer,
    cache_dir: str | None = None,
) -> str:
    """Return a short business-context note for the buyer (cached)."""
    name = config.BUYER_NAME if name is None else name
    website = config.BUYER_WEBSITE if website is None else website
    cache_dir = config.WEB_CONTEXT_CACHE_DIR if cache_dir is None else cache_dir
    if not name and not website:
        return ""
    key = f"buyer-{name}|{website}"
    cached = _read_cache(cache_dir, key)
    if cached is not None:
        return cached
    note = summarize_fn(name or website, scrape_fn(website) if website else "")
    _write_cache(cache_dir, key, note)
    return note


def get_product_context(
    line_items: list,
    vendor_name: str,
    *,
    search_fn: Callable[[str], list[dict]] = _ddg_search,
    summarize_fn: Callable[[list[tuple[str, str]]], str] = _summarize_products,
    cache_dir: str | None = None,
) -> str:
    """Web-search each line item (cached per query) and summarize into a note."""
    cache_dir = config.WEB_CONTEXT_CACHE_DIR if cache_dir is None else cache_dir
    if not line_items:
        return ""
    items_with_snippets: list[tuple[str, str]] = []
    for item in line_items:
        query = f"{vendor_name} {item.description}".strip()
        cached = _read_cache(cache_dir, f"product-{query}")
        if cached is None:
            results = search_fn(query)
            cached = " | ".join(r.get("body", "") for r in results) or "no info found"
            _write_cache(cache_dir, f"product-{query}", cached)
        items_with_snippets.append((item.description, cached))
    return summarize_fn(items_with_snippets)


def _summarize_supplier(name: str, snippets: str) -> str:
    """One or two sentences on what a supplier sells."""
    if not snippets.strip() or snippets == "no info found":
        return ""
    prompt = (
        f"In one or two sentences, state what the company '{name}' sells or does "
        "— its industry and its main products or services. Write nothing about "
        "any customer of theirs. If the snippets do not identify the company, "
        "reply with exactly: UNKNOWN\n\n"
        f"{snippets[:4000]}"
    )
    try:
        note = config.get_llm().call(messages=[{"role": "user", "content": prompt}]).strip()
    except Exception:  # noqa: BLE001
        return ""
    return "" if note.upper().startswith("UNKNOWN") else note


def get_supplier_context(
    name: str,
    country_code: str | None = None,
    *,
    search_fn: Callable[[str], list[dict]] = _ddg_search,
    summarize_fn: Callable[[str, str], str] = _summarize_supplier,
    cache_dir: str | None = None,
) -> str:
    """What this supplier sells, from a web search of its name (cached)."""
    if not (name or "").strip():
        return ""
    cache_dir = config.WEB_CONTEXT_CACHE_DIR if cache_dir is None else cache_dir
    query = " ".join(part for part in (name, country_code, "company what they sell") if part)
    key = f"supplier-{query}"
    cached = _read_cache(cache_dir, key)
    if cached is None:
        results = search_fn(query)
        cached = " | ".join(r.get("body", "") for r in results) or "no info found"
        _write_cache(cache_dir, key, cached)
    return summarize_fn(name, cached)
