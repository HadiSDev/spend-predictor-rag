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


def get_llm() -> LLM:
    """Return a CrewAI LLM pointed at the local vLLM OpenAI-compatible endpoint."""
    return LLM(
        model=VLLM_MODEL,
        base_url=VLLM_BASE_URL,
        api_key=VLLM_API_KEY,
        max_tokens=VLLM_MAX_TOKENS,
        timeout=VLLM_TIMEOUT,
    )
