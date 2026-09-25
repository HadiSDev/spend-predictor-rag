"""The shared LLM reads documents; it does not write prose."""
from __future__ import annotations

import inspect

from ai_api import config
from ai_api.synthdata import content


def test_the_shared_llm_is_deterministic_by_default():
    assert config.VLLM_TEMPERATURE == 0.0


def test_the_temperature_reaches_the_client():
    assert config.get_llm().temperature == 0.0


def test_the_synthetic_data_generator_keeps_its_own_llm():
    assert "config.get_llm" not in inspect.getsource(content), (
        "synthdata must build its own LLM — see the variation bar in CLAUDE.md"
    )
