"""The shared LLM reads documents; it does not write prose.

No temperature was ever set, so every call inherited the server's default — and
the effect was visible on real data: the *same* DSB screenshot was read correctly
on one run of the document stage and came back with no amounts at all on the
next. An invoice that processes or fails depending on the roll of a sampler is
worse than one that fails consistently, because nobody can tell whether a fix
worked.

Every consumer of :func:`ai_api.config.get_llm` is a reading task — extracting an
invoice, categorizing a line, summarizing a supplier's page. None of them wants
variety. The synthetic-data generator, which genuinely does, builds its own LLM
and is deliberately untouched by this.
"""
from __future__ import annotations

from ai_api import config


def test_the_shared_llm_is_deterministic_by_default():
    assert config.VLLM_TEMPERATURE == 0.0


def test_the_temperature_reaches_the_client():
    """A constant nothing passes to the model would be a comment, not a setting."""
    assert config.get_llm().temperature == 0.0


def test_the_synthetic_data_generator_keeps_its_own_llm():
    """Variety is the point there, so it must not inherit this determinism."""
    import inspect

    from ai_api.synthdata import content

    assert "config.get_llm" not in inspect.getsource(content), (
        "synthdata must build its own LLM — see the variation bar in CLAUDE.md"
    )
