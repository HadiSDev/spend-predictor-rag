"""Environment configuration and the vLLM LLM factory."""
from __future__ import annotations

import os
from pathlib import Path

from crewai import LLM
from dotenv import load_dotenv

load_dotenv()

# repo root = .../spend-predictor-rag (config.py is at src/spend_predictor/config.py)
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

CHART_OF_ACCOUNTS_PATH = os.getenv(
    "CHART_OF_ACCOUNTS_PATH", str(PROJECT_ROOT / "data" / "chart_of_accounts.csv")
)
INVOICES_DIR = os.getenv("INVOICES_DIR", str(PROJECT_ROOT / "data" / "invoices"))
LEDGER_PATH = os.getenv("LEDGER_PATH", str(PROJECT_ROOT / "output" / "ledger.csv"))
CHROMA_DIR = os.getenv("CHROMA_DIR", str(PROJECT_ROOT / "chroma_db"))


def get_llm() -> LLM:
    """Return a CrewAI LLM pointed at the local vLLM OpenAI-compatible endpoint."""
    return LLM(
        model=VLLM_MODEL,
        base_url=VLLM_BASE_URL,
        api_key=VLLM_API_KEY,
        max_tokens=VLLM_MAX_TOKENS,
        timeout=VLLM_TIMEOUT,
    )
