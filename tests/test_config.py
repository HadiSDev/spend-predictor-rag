from pathlib import Path

from spend_predictor import config


def test_default_paths_resolve_under_project_root():
    root = config.PROJECT_ROOT
    assert Path(config.CHART_OF_ACCOUNTS_PATH) == root / "data" / "chart_of_accounts.csv"
    assert Path(config.INVOICES_DIR) == root / "data" / "invoices"
    assert Path(config.LEDGER_PATH) == root / "output" / "ledger.csv"
    assert Path(config.CHROMA_DIR) == root / "chroma_db"


def test_get_llm_uses_vllm_settings():
    llm = config.get_llm()
    # CrewAI strips the "hosted_vllm/" provider prefix when storing the model name
    assert llm.model == "google/gemma-4-E4B-it"
    assert llm.base_url == config.VLLM_BASE_URL
    # VLLM_MODEL uses the hosted_vllm/ prefix required by this version of crewAI
    assert config.VLLM_MODEL == "hosted_vllm/google/gemma-4-E4B-it"
    assert config.VLLM_BASE_URL == "http://localhost:8000/v1"


def test_get_llm_bounds_generation_and_timeout():
    # Without these, a structured-output call can run toward the model's full
    # context window and hang the pipeline (observed in the live smoke test).
    llm = config.get_llm()
    assert llm.max_tokens == config.VLLM_MAX_TOKENS
    assert float(llm.timeout) == float(config.VLLM_TIMEOUT)
    assert config.VLLM_MAX_TOKENS == 8192
    assert config.VLLM_TIMEOUT == 120


def test_buyer_and_web_context_settings():
    import os
    from pathlib import Path
    assert config.BUYER_NAME == os.getenv("BUYER_NAME", "")
    assert config.BUYER_WEBSITE == os.getenv("BUYER_WEBSITE", "")
    assert config.PRODUCT_SEARCH_MAX_RESULTS == int(os.getenv("PRODUCT_SEARCH_MAX_RESULTS", "3"))
    assert Path(config.WEB_CONTEXT_CACHE_DIR) == Path(
        os.getenv("WEB_CONTEXT_CACHE_DIR", str(config.PROJECT_ROOT / "data" / "web_cache"))
    )
