"""Environment configuration and the vLLM LLM factory for the AI service."""
from __future__ import annotations

import os
from pathlib import Path

from crewai import LLM
from dotenv import load_dotenv

from web_api import config as _web_config

load_dotenv()

_TRUTHY = ("1", "true", "yes", "on")


def _env_flag(name: str) -> bool:
    """Whether the environment variable ``name`` is set to a truthy value."""
    return os.getenv(name, "false").lower() in _TRUTHY


PROJECT_ROOT = Path(__file__).resolve().parents[4]

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "hosted_vllm/google/gemma-4-E4B-it")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "not-needed")
VLLM_MAX_TOKENS = int(os.getenv("VLLM_MAX_TOKENS", "8192"))
VLLM_TIMEOUT = int(os.getenv("VLLM_TIMEOUT", "120"))

VLLM_TEMPERATURE = float(os.getenv("VLLM_TEMPERATURE", "0.0"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

BUYER_NAME = os.getenv("BUYER_NAME", "")
BUYER_WEBSITE = os.getenv("BUYER_WEBSITE", "")
WEB_CONTEXT_CACHE_DIR = os.getenv(
    "WEB_CONTEXT_CACHE_DIR", str(PROJECT_ROOT / "data" / "web_cache")
)
PRODUCT_SEARCH_MAX_RESULTS = int(os.getenv("PRODUCT_SEARCH_MAX_RESULTS", "3"))

VENDOR_ENRICHMENT_ENABLED = _env_flag("VENDOR_ENRICHMENT_ENABLED")

CATEGORY_RETRIEVAL_ENABLED = _env_flag("CATEGORY_RETRIEVAL_ENABLED")
CATEGORY_RETRIEVAL_TOP_K = int(os.getenv("CATEGORY_RETRIEVAL_TOP_K", "5"))

CHART_OF_ACCOUNTS_PATH = os.getenv(
    "CHART_OF_ACCOUNTS_PATH", str(PROJECT_ROOT / "data" / "chart_of_accounts.csv")
)
INVOICES_DIR = os.getenv("INVOICES_DIR", str(PROJECT_ROOT / "data" / "invoices"))
LEDGER_PATH = os.getenv("LEDGER_PATH", str(PROJECT_ROOT / "output" / "ledger.csv"))
CHROMA_DIR = os.getenv("CHROMA_DIR", str(PROJECT_ROOT / "chroma_db"))

INVOICE_CONCURRENCY = int(os.getenv("INVOICE_CONCURRENCY", "4"))

DOC_MAX_ATTEMPTS = int(os.getenv("DOC_MAX_ATTEMPTS", "3"))

DOC_RECONCILE_TOLERANCE_PCT = _web_config.DOC_RECONCILE_TOLERANCE_PCT
DOC_RECONCILE_TOLERANCE_ABS = _web_config.DOC_RECONCILE_TOLERANCE_ABS
DOC_INTERNAL_TOLERANCE_PCT = _web_config.DOC_INTERNAL_TOLERANCE_PCT
DOC_INTERNAL_TOLERANCE_ABS = _web_config.DOC_INTERNAL_TOLERANCE_ABS

DOC_STALE_CLAIM_MINUTES = int(os.getenv("DOC_STALE_CLAIM_MINUTES", "60"))

DOC_VISION_MAX_PAGES = int(os.getenv("DOC_VISION_MAX_PAGES", "8"))

DOC_VISION_MAX_EDGE = int(os.getenv("DOC_VISION_MAX_EDGE", "1600"))

DOC_VISION_PAGE_BANDS = int(os.getenv("DOC_VISION_PAGE_BANDS", "3"))

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
