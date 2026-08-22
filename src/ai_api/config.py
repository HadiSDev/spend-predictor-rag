"""Environment configuration and the vLLM LLM factory for the AI service."""
from __future__ import annotations

import os
from pathlib import Path

from crewai import LLM
from dotenv import load_dotenv

from web_api import config as _web_config

load_dotenv()

# repo root = .../spend-predictor-rag (config.py is at src/ai_api/config.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "hosted_vllm/google/gemma-4-E4B-it")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "not-needed")
# Bound generation and wall-clock per LLM call. Without max_tokens a structured
# response can run toward the model's full context (hanging the pipeline); the
# timeout is a safety net so a stalled request fails instead of blocking forever.
VLLM_MAX_TOKENS = int(os.getenv("VLLM_MAX_TOKENS", "8192"))
VLLM_TIMEOUT = int(os.getenv("VLLM_TIMEOUT", "120"))

# Every consumer of `get_llm()` is a *reading* task — extracting an invoice,
# categorizing a line, summarizing a supplier's page — and none of them wants
# variety. Left unset, calls inherited the server's default and the effect was
# visible on real data: the same DSB screenshot was read correctly on one run of
# the document stage and came back with no amounts on the next. An invoice whose
# fate turns on a sampler is worse than one that fails consistently, because
# nobody can tell whether a fix worked. The synthetic-data generator, which does
# want variety, builds its own LLM and is untouched by this.
VLLM_TEMPERATURE = float(os.getenv("VLLM_TEMPERATURE", "0.0"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Qdrant vector store (replaces ChromaDB)
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

# Buyer is known beforehand (backend provides name + website); see the
# hierarchical-categorization spec. Direct/Indirect is judged from this context.
BUYER_NAME = os.getenv("BUYER_NAME", "")
BUYER_WEBSITE = os.getenv("BUYER_WEBSITE", "")
WEB_CONTEXT_CACHE_DIR = os.getenv(
    "WEB_CONTEXT_CACHE_DIR", str(PROJECT_ROOT / "data" / "web_cache")
)
PRODUCT_SEARCH_MAX_RESULTS = int(os.getenv("PRODUCT_SEARCH_MAX_RESULTS", "3"))

CHART_OF_ACCOUNTS_PATH = os.getenv(
    "CHART_OF_ACCOUNTS_PATH", str(PROJECT_ROOT / "data" / "chart_of_accounts.csv")
)
INVOICES_DIR = os.getenv("INVOICES_DIR", str(PROJECT_ROOT / "data" / "invoices"))
LEDGER_PATH = os.getenv("LEDGER_PATH", str(PROJECT_ROOT / "output" / "ledger.csv"))
CHROMA_DIR = os.getenv("CHROMA_DIR", str(PROJECT_ROOT / "chroma_db"))

# Invoices are independent, so the batch runs them concurrently (the work is
# I/O-bound: HTTP to vLLM + web scrape/search). Tune to what your vLLM server
# handles; 1 means strictly sequential (deterministic ledger order).
INVOICE_CONCURRENCY = int(os.getenv("INVOICE_CONCURRENCY", "4"))

# -- Document processing stage (python -m ai_api.documents.runner) -----------

# How many times one invoice may be attempted before the stage stops picking it
# up. A document that has failed this often will not start succeeding on its own;
# the way back is POST /invoices/{id}/reprocess, which resets the count.
DOC_MAX_ATTEMPTS = int(os.getenv("DOC_MAX_ATTEMPTS", "3"))

# How far the extracted lines may be from the invoice's own total before the
# extraction is rejected. Re-exported from `web_api.config`, which owns them:
# the same tolerance decides whether a *human's* corrected lines reconcile, and
# a second copy of the rule would eventually disagree with the first. The env
# var names are unchanged. Monkeypatch `web_api.config`, not this module — the
# rule reads its values there.
DOC_RECONCILE_TOLERANCE_PCT = _web_config.DOC_RECONCILE_TOLERANCE_PCT
DOC_RECONCILE_TOLERANCE_ABS = _web_config.DOC_RECONCILE_TOLERANCE_ABS

# An invoice claimed for processing whose run died leaves it stuck in
# `processing` forever. After this long a claim is treated as abandoned and the
# invoice is picked up again.
DOC_STALE_CLAIM_MINUTES = int(os.getenv("DOC_STALE_CLAIM_MINUTES", "60"))

# A document with no text layer — a photo, a screenshot, a scan — is read by
# showing it to the model rather than by refusing it. Two bounds keep that
# affordable, and both are read through this module at call time so a test (and
# an operator) can move them:
#
# How many pages of one document are rendered. A page is an image and an image
# is thousands of tokens, so an unbounded statement would overflow the context
# window and fail an invoice we could otherwise have read. Invoices are short;
# the cap bites on bank statements, where the first pages carry the header.
DOC_VISION_MAX_PAGES = int(os.getenv("DOC_VISION_MAX_PAGES", "8"))

# The longest edge, in pixels, of an image sent to the model. A phone photo is
# ~4000px wide and a receipt holds nothing at that resolution; the vision
# encoder charges for the pixels either way. Pages are rendered straight to this
# size rather than rendered large and shrunk.
DOC_VISION_MAX_EDGE = int(os.getenv("DOC_VISION_MAX_EDGE", "1600"))

# How many horizontal bands each rendered page is cut into, each one given the
# full pixel budget above — so a page is effectively read at this many times the
# resolution. An EKWB credit memo, machine-generated and legible at a glance,
# returned null amounts every time it was shown whole: its price column is a
# handful of pixels tall at a 1600px page height. At three bands the band
# holding the table read every line correctly and the invoice reconciled. Two
# was tried first and missed the shipping line, so three is the number that
# worked rather than the number that sounded right.
DOC_VISION_PAGE_BANDS = int(os.getenv("DOC_VISION_PAGE_BANDS", "3"))

# The ceiling on images sent for one document, since banding multiplies them and
# each is thousands of tokens (3x on each edge is 9x the pixels). Bounds the
# cost of a long document; what it discards is logged, never dropped silently.
DOC_VISION_MAX_IMAGES = int(os.getenv("DOC_VISION_MAX_IMAGES", "12"))


def get_llm() -> LLM:
    """Return a CrewAI LLM pointed at the local vLLM OpenAI-compatible endpoint."""
    return LLM(
        model=VLLM_MODEL,
        base_url=VLLM_BASE_URL,
        api_key=VLLM_API_KEY,
        max_tokens=VLLM_MAX_TOKENS,
        timeout=VLLM_TIMEOUT,
        temperature=VLLM_TEMPERATURE,
    )
